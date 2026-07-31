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
from app.features.ocr.table_html_parser import find_item_rows, parse_table_rows

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


def build_line_items(item_rows: list[list[tuple[str, int]]]) -> list[dict[str, str | None]]:
    items = []
    for row in item_rows:
        sr_no, description, hsn_sac, basic, quantity, amount = (text or None for text, _ in row)
        # PP-Structure occasionally emits a spurious duplicate/blank row right at the item/
        # summary boundary. Every real item row has a description; a ghost row does not.
        if description is None:
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
    return items


async def process_part2(file_bytes: bytes, mime_type: str) -> dict[str, Any]:
    # Unlike Part 1's flat-text OCR, generic OpenCV preprocessing (deskew/CLAHE/lighting-
    # normalize) was confirmed to degrade PP-Structure's table cell detection on real samples
    # - it subtly shifts empty-cell positions, corrupting column alignment. PP-Structure has
    # its own internal doc-orientation classification, so the raw image is used as-is.
    image = _load_image_for_ocr(file_bytes, mime_type)

    timeout = (
        TABLE_TIMEOUT_SECONDS_PDF if mime_type == "application/pdf" else TABLE_TIMEOUT_SECONDS_IMAGE
    )
    tables, page_text = await asyncio.wait_for(
        asyncio.to_thread(analyze_page, image), timeout=timeout
    )

    multi_page = detect_multi_page(page_text)

    if not tables:
        return {"lineItems": [], **_EMPTY_SUMMARY, "multiPage": multi_page, "tableDetected": False}

    rows = parse_table_rows(tables[0])
    item_rows = find_item_rows(rows)
    line_items = build_line_items(item_rows)

    # The full-page text (not just the detected table's summary rows) is used here since some
    # real samples have the tax-summary totals sit right at the table's visual edge and get
    # excluded from the detected table bounding box entirely.
    summary = await extract_part2_summary(page_text) if page_text.strip() else dict(_EMPTY_SUMMARY)

    return {"lineItems": line_items, **summary, "multiPage": multi_page, "tableDetected": True}
