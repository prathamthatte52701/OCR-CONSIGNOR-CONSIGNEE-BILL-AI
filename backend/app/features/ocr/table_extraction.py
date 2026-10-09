"""Part 2 pipeline orchestrator: preprocess -> PP-Structure table detection -> deterministic
row parsing for the unambiguous item columns -> Groq-assisted structuring only for the messy
tax-summary section (the AI is unreliable at faithfully preserving raw HTML column position,
so it is used only where genuine ambiguity remains, not for the well-structured item rows)."""

import asyncio
import re
from typing import Any

from app.features.ocr import preprocessing
from app.features.ocr.ai_extraction import extract_part2_summary
from app.features.ocr.ppstructure_runner import analyze_page
from app.features.ocr.table_html_parser import (
    Row,
    find_item_rows,
    parse_table_rows,
    read_item_row,
)

# "Page 1 of 2" (or higher) means the item table continues on a page not in this upload.
_PAGE_OF_RE = re.compile(r"Page\s*(\d+)\s*of\s*(\d+)", re.IGNORECASE)

# PP-Structure loads many more sub-models (layout, table classification, wired/wireless
# cell detection) than plain OCR, and the first inference in a process is measurably slower
# even with weights already cached on disk - a plain OCR-sized timeout was cutting this off.
TABLE_TIMEOUT_SECONDS_IMAGE = 300
TABLE_TIMEOUT_SECONDS_PDF = 420

_EMPTY_SUMMARY: dict[str, Any] = {
    "totalBasicAmount": None,
    "cgstRate": None,
    "cgstAmount": None,
    "sgstRate": None,
    "sgstAmount": None,
    "igstRate": None,
    "igstAmount": None,
    "totalAmount": None,
}


def _load_image_for_ocr(file_bytes: bytes, mime_type: str) -> Any:
    if mime_type == "application/pdf":
        return preprocessing.render_pdf_first_page(file_bytes)
    return preprocessing.load_image_bytes(file_bytes)


def detect_multi_page(page_text: str) -> bool:
    match = _PAGE_OF_RE.search(page_text)
    if match is None:
        return False
    total_pages = int(match.group(2))
    return total_pages > 1


# Every real item description on this template starts with an uppercase item-code
# abbreviation (SC, HOB, GSC, SHANK, STEP...) optionally preceded by its SR No. Only
# treat a leading 1-2 digit number as the SR No if it's immediately followed by that
# pattern - a naive "first digit found" match would wrongly grab a digit from within the
# description itself (e.g. the "9" in "SC DRILL 9.0xFL61...").
_SR_NO_DESCRIPTION_RE = re.compile(r"^\s*(\d{1,2})\s+(?=[A-Z]{2,})")


def _split_sr_no_description(merged: str | None) -> tuple[str | None, str | None]:
    if merged is None:
        return None, None
    match = _SR_NO_DESCRIPTION_RE.match(merged)
    if match:
        return match.group(1), merged[match.end() :].strip()
    return None, merged.strip()


def _number(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(re.sub(r"[,\s]", "", value))
    except ValueError:
        return None


def _repair_quantity(items: list[dict[str, str | None]]) -> None:
    """On this form amount = basic x quantity. The quantity digit is printed small and light
    and is often lost (None) or misread by the cell OCR, so when quantity is not a whole
    number that explains amount from basic, a whole-number amount / basic ratio replaces it.
    Never touches a quantity that already agrees, and never invents one when basic or amount
    is missing."""
    for item in items:
        basic, amount = _number(item["basic"]), _number(item["amount"])
        if not basic or not amount:
            continue
        quantity = _number(item["quantity"])
        if quantity is not None and abs(basic * quantity - amount) < 0.01:
            continue
        ratio = amount / basic
        if 0 < round(ratio) < 1000 and abs(ratio - round(ratio)) < 1e-9:
            item["quantity"] = str(round(ratio))


def build_line_items(
    item_rows: list[tuple[Row, dict[str, int]]],
) -> list[dict[str, str | None]]:
    items = []
    for row, column_map in item_rows:
        # Fields are read by their actual logical column position (see
        # table_html_parser.build_column_map/read_row_by_column_map) - this table's
        # detected column ORDER and per-cell colspan both vary between real documents, so
        # there is no fixed left-to-right position that's safe to assume.
        fields = read_item_row(row, column_map)
        sr_no = fields.get("srNo")
        description = fields.get("description")
        hsn_sac = fields.get("hsnSac")
        basic = fields.get("basic")
        quantity = fields.get("quantity")
        amount = fields.get("amount")

        # If this table's header had no separate SR No column at all (the faint divider
        # between the narrow SR No cell and the wide Description cell wasn't detected, so
        # they merged into one header cell/text), a leading "<digit(s)> <ITEM-CODE>" in the
        # description is the SR No hiding inside it - split it back out.
        if sr_no is None and description is not None:
            sr_no, description = _split_sr_no_description(description)

        # PP-Structure occasionally emits a spurious duplicate/blank row right at the item/
        # summary boundary. Every real item row has a description; a ghost row does not.
        if not description:
            continue
        items.append(
            {
                "srNo": sr_no,
                "description": description,
                "hsnSac": hsn_sac,
                "basic": basic,
                "quantity": quantity,
                "amount": amount,
            }
        )
    _repair_quantity(items)
    return items


async def process_part2(file_bytes: bytes, mime_type: str) -> dict[str, Any]:
    # Unlike Part 1's flat-text OCR, generic OpenCV preprocessing (deskew/CLAHE/lighting-
    # normalize/upscale) was confirmed to degrade PP-Structure's table cell detection on real
    # samples - it subtly shifts empty-cell positions, corrupting column alignment, and even
    # upscaling a genuinely low-res page recovered 0/3 table detections while shortening OCR
    # text on 2/3 (see preprocessing.py: PART_ALLOWED_STEPS). PP-Structure has its own internal
    # doc-orientation classification, so gross rotation needs nothing here either. The shared
    # quality gate therefore runs with part=2, which allows zero steps through - every metric is
    # still measured and logged (useful for debugging a bad extraction), but the image passed
    # to PP-Structure is always byte-for-byte identical to the input, exactly as before.
    image = _load_image_for_ocr(file_bytes, mime_type)
    image, _report = preprocessing.prepare_for_ocr(image, part=2)

    timeout = (
        TABLE_TIMEOUT_SECONDS_PDF if mime_type == "application/pdf" else TABLE_TIMEOUT_SECONDS_IMAGE
    )
    tables, page_text = await asyncio.wait_for(
        asyncio.to_thread(analyze_page, image), timeout=timeout
    )

    multi_page = detect_multi_page(page_text)

    if not tables:
        return {"lineItems": [], **_EMPTY_SUMMARY, "multiPage": multi_page, "tableDetected": False}

    # A page can come back as several tables (e.g. a footer block split off, or the item rows
    # in the second one); the item table is the one that actually yields item rows.
    line_items: list[dict[str, str | None]] = []
    for table in tables:
        candidate = build_line_items(find_item_rows(parse_table_rows(table)))
        if len(candidate) > len(line_items):
            line_items = candidate

    # The full-page text (not just the detected table's summary rows) is used here since some
    # real samples have the tax-summary totals sit right at the table's visual edge and get
    # excluded from the detected table bounding box entirely.
    summary = await extract_part2_summary(page_text) if page_text.strip() else dict(_EMPTY_SUMMARY)

    return {"lineItems": line_items, **summary, "multiPage": multi_page, "tableDetected": True}
