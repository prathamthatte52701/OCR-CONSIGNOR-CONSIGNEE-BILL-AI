"""Part 1 pipeline orchestrator: preprocess -> OCR -> column split -> AI extraction.

The Part 1 form is a two-column table (Consignee left, Consignor right). Flat OCR reading
order interleaves the two columns' lines, which is ambiguous for fields that share a label
in both columns (both blocks have their own "Address" and "State Code" rows). Splitting OCR
lines into left/right columns by their bounding-box x-coordinate before handing text to the
AI removes that ambiguity entirely, rather than hoping the AI infers structure from text.
"""

import asyncio
from typing import Any

from app.features.ocr import preprocessing
from app.features.ocr.ai_extraction import extract_part1_header
from app.features.ocr.paddle_runner import (
    OCR_TIMEOUT_SECONDS_IMAGE,
    OCR_TIMEOUT_SECONDS_PDF,
    run_ocr,
)


def _load_image_for_ocr(file_bytes: bytes, mime_type: str) -> Any:
    if mime_type == "application/pdf":
        return preprocessing.render_pdf_first_page(file_bytes)
    return preprocessing.load_image_bytes(file_bytes)


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

    # Preserve top-to-bottom reading order within each column.
    left_lines.sort(key=lambda line: line["box"][1])
    right_lines.sort(key=lambda line: line["box"][1])

    left_text = "\n".join(line["text"] for line in left_lines)
    right_text = "\n".join(line["text"] for line in right_lines)
    return left_text, right_text


async def process_part1(file_bytes: bytes, mime_type: str) -> dict[str, Any]:
    image = _load_image_for_ocr(file_bytes, mime_type)
    processed = preprocessing.assess_and_preprocess(image)

    timeout = (
        OCR_TIMEOUT_SECONDS_PDF if mime_type == "application/pdf" else OCR_TIMEOUT_SECONDS_IMAGE
    )
    lines = await asyncio.wait_for(asyncio.to_thread(run_ocr, processed), timeout=timeout)

    consignee_text, consignor_text = split_into_columns(lines)
    extracted = await extract_part1_header(consignee_text, consignor_text)
    return extracted
