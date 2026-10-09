"""Part 1 pipeline orchestrator: preprocess -> OCR -> column split -> AI extraction.

The Part 1 form is a two-column table (Consignee left, Consignor right). Flat OCR reading
order interleaves the two columns' lines, which is ambiguous for fields that share a label
in both columns (both blocks have their own "Address" and "State Code" rows). Splitting OCR
lines into left/right columns by their bounding-box x-coordinate before handing text to the
AI removes that ambiguity entirely, rather than hoping the AI infers structure from text.
"""

import asyncio
from typing import Any

import cv2

from loguru import logger

from app.features.ocr import preprocessing
from app.features.ocr.ai_extraction import extract_part1_header
from app.features.ocr.paddle_runner import (
    OCR_TIMEOUT_SECONDS_IMAGE,
    OCR_TIMEOUT_SECONDS_PDF,
    run_ocr,
)
from app.features.ocr.page_normalize import normalize_photo


def _load_image_for_ocr(file_bytes: bytes, mime_type: str) -> Any:
    if mime_type == "application/pdf":
        return preprocessing.render_pdf_first_page(file_bytes)
    return preprocessing.load_image_bytes(file_bytes)


# A box joins a row when its vertical centre is within this fraction of its own height.
ROW_TOLERANCE = 0.6


def split_into_columns(lines: list[dict[str, Any]]) -> tuple[str, str]:
    """Buckets OCR lines into left/right columns by box center-x vs page midpoint,
    preserving each column's own top-to-bottom order."""
    if not lines:
        return "", ""

    max_x = max(line["box"][2] for line in lines)
    min_x = min(line["box"][0] for line in lines)
    midpoint = (min_x + max_x) / 2

    left_lines = [line for line in lines if (line["box"][0] + line["box"][2]) / 2 <= midpoint]
    right_lines = [line for line in lines if (line["box"][0] + line["box"][2]) / 2 > midpoint]

    left_text = _rows_to_text(left_lines)
    right_text = _rows_to_text(right_lines)
    return left_text, right_text


def _rows_to_text(column_lines: list[dict[str, Any]]) -> str:
    """Top-to-bottom text for one column with each printed row on ONE line ("label  value").
    Sorting by box top alone put a value before its label whenever the photo was slightly
    tilted or the two boxes differed in height, and the AI then shifted values by one line."""
    ordered = sorted(column_lines, key=lambda line: (line["box"][1] + line["box"][3]) / 2)
    rows: list[list[dict[str, Any]]] = []
    for line in ordered:
        center = (line["box"][1] + line["box"][3]) / 2
        height = max(line["box"][3] - line["box"][1], 1)
        if rows:
            row_center = sum((m["box"][1] + m["box"][3]) / 2 for m in rows[-1]) / len(rows[-1])
            if abs(center - row_center) <= ROW_TOLERANCE * height:
                rows[-1].append(line)
                continue
        rows.append([line])
    return "\n".join(
        "  ".join(m["text"] for m in sorted(row, key=lambda m: m["box"][0])) for row in rows
    )


async def _normalize_photo_page(file_bytes: bytes) -> bytes:
    """Phone photos only: finds the paper in a photo with background around it and flattens
    it to an upright rectangle. A scan or a tight photo comes back as the original bytes,
    untouched. Never raises - any problem falls back to the original upload. Rotation is not
    handled here: PaddleOCR's own doc-orientation classifier already covers 90/180/270."""
    try:
        page_bytes, steps = await asyncio.to_thread(normalize_photo, file_bytes, None)
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"Photo page normalization failed, using original: {exc}")
        return file_bytes
    if steps:
        logger.info(f"Photo page normalization: {steps}")
    return page_bytes


async def process_part1(file_bytes: bytes, mime_type: str) -> dict[str, Any]:
    if mime_type != "application/pdf":
        file_bytes = await _normalize_photo_page(file_bytes)
    image = _load_image_for_ocr(file_bytes, mime_type)
    processed, _report = preprocessing.prepare_for_ocr(image, part=1)
    # White margin: the text detector misses a line that touches the photo edge (e.g. "Reason").
    processed = cv2.copyMakeBorder(
        processed, 40, 80, 40, 40, cv2.BORDER_CONSTANT, value=(255, 255, 255)
    )

    timeout = (
        OCR_TIMEOUT_SECONDS_PDF if mime_type == "application/pdf" else OCR_TIMEOUT_SECONDS_IMAGE
    )
    lines = await asyncio.wait_for(asyncio.to_thread(run_ocr, processed), timeout=timeout)

    consignee_text, consignor_text = split_into_columns(lines)
    extracted = await extract_part1_header(consignee_text, consignor_text)
    return extracted
