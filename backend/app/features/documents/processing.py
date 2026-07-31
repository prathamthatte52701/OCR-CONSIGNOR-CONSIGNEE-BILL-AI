"""Runs the full pipeline (Part1 OCR + Part2 PP-Structure) and applies the deterministic
correction layer to every extracted field, producing the flat dict that gets $set into the
document's Mongo record."""

from typing import Any

from app.features.ocr.extraction import (
    LINE_ITEM_FIELD_CLASSES,
    PART1_FIELD_CLASSES,
    PART2_SUMMARY_FIELD_CLASSES,
    FieldClass,
    correct_field,
    extract_pincode,
)
from app.features.ocr.pipeline import process_part1
from app.features.ocr.table_extraction import process_part2

LOW_CONFIDENCE_THRESHOLD = 80


def _apply_corrections(raw: dict[str, Any], field_classes: dict[str, FieldClass]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for field, field_class in field_classes.items():
        correction = correct_field(raw.get(field), field_class)
        result[field] = correction.value
        result[f"{field}Confidence"] = correction.confidence
        if field_class not in (FieldClass.FREE_TEXT_LIGHT,):
            result[f"{field}AutoCorrected"] = correction.auto_corrected
    return result


def _apply_pincode_correction(prefix: str, address: str | None) -> dict[str, Any]:
    pincode = extract_pincode(address)
    correction = correct_field(pincode, FieldClass.ALL_DIGITS)
    return {
        f"{prefix}Pincode": correction.value,
        f"{prefix}PincodeConfidence": correction.confidence,
        f"{prefix}PincodeAutoCorrected": correction.auto_corrected,
    }


def _apply_line_item_corrections(raw_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [_apply_corrections(item, LINE_ITEM_FIELD_CLASSES) for item in raw_items]


def _has_low_confidence(fields: dict[str, Any]) -> bool:
    return any(
        value < LOW_CONFIDENCE_THRESHOLD
        for key, value in fields.items()
        if key.endswith("Confidence") and isinstance(value, int)
    )


async def run_full_pipeline(
    part1_bytes: bytes, part1_mime: str, part2_bytes: bytes, part2_mime: str
) -> dict[str, Any]:
    raw_part1 = await process_part1(part1_bytes, part1_mime)
    raw_part2 = await process_part2(part2_bytes, part2_mime)

    update: dict[str, Any] = _apply_corrections(raw_part1, PART1_FIELD_CLASSES)
    update.update(_apply_pincode_correction("consignee", raw_part1.get("consigneeAddress")))
    update.update(_apply_pincode_correction("consignor", raw_part1.get("consignorAddress")))

    update["lineItems"] = _apply_line_item_corrections(raw_part2.get("lineItems", []))
    update.update(_apply_corrections(raw_part2, PART2_SUMMARY_FIELD_CLASSES))
    update["multiPage"] = bool(raw_part2.get("multiPage", False))

    line_item_confidences = {
        f"lineItem{i}.{k}": v for i, item in enumerate(update["lineItems"]) for k, v in item.items()
    }
    update["hasLowConfidenceFields"] = _has_low_confidence(update) or _has_low_confidence(
        line_item_confidences
    )

    return update
