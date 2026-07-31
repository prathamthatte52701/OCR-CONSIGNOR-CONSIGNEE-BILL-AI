"""Runs the full pipeline (Part1 OCR + Part2 PP-Structure) and applies the deterministic
correction layer to every extracted field, producing the flat dict that gets $set into the
document's Mongo record."""

import re
from typing import Any

from app.features.ocr.extraction import (
    CONFIDENCE_CORRECTED,
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

# On every real sample seen so far, PO No always starts "3242..." and Request No is
# always zero-padded starting "0000...". PO No and Request No sit on adjacent lines in
# the CONSIGNOR column and the AI occasionally reads one label's value into the other
# field. This is a pure safety net: it only fires on the specific, unambiguous shape of
# that mistake (one field holds the other's pattern while its own is missing) and never
# invents a value that wasn't actually read.
_PO_NO_RE = re.compile(r"^3242\d+$")
_REQUEST_NO_RE = re.compile(r"^0000\d+$")


def _apply_po_request_swap_safety_net(raw: dict[str, Any]) -> dict[str, Any]:
    po_no = raw.get("consignorPoNo")
    request_no = raw.get("requestNo")

    if request_no is None and isinstance(po_no, str):
        po_looks_like_request_no = _REQUEST_NO_RE.fullmatch(po_no) is not None
        po_looks_like_po_no = _PO_NO_RE.fullmatch(po_no) is not None
        if po_looks_like_request_no and not po_looks_like_po_no:
            return {**raw, "consignorPoNo": None, "requestNo": po_no}

    if po_no is None and isinstance(request_no, str):
        request_looks_like_po_no = _PO_NO_RE.fullmatch(request_no) is not None
        request_looks_like_request_no = _REQUEST_NO_RE.fullmatch(request_no) is not None
        if request_looks_like_po_no and not request_looks_like_request_no:
            return {**raw, "consignorPoNo": request_no, "requestNo": None}

    return raw


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


def _parse_money(value: Any) -> float | None:
    if not isinstance(value, str):
        return None
    try:
        return float(value.replace(",", ""))
    except ValueError:
        return None


def _format_money(value: float) -> str:
    return f"{value:,.2f}"


# _parse_money/FieldClass.MONEY both accept "1,40000" (digits+commas, no decimal
# required) as a parseable number - that shape is itself evidence of an OCR misread on
# this template, where every real amount is printed "1,234.00" (exactly two decimals,
# correct thousands grouping). Used to gate which values are trustworthy enough to be
# an ANCHOR for deriving another field - never to reject a value from being displayed.
_WELL_FORMED_MONEY_RE = re.compile(r"^\d{1,3}(,\d{3})*\.\d{2}$")


def _is_trustworthy_money(value: Any) -> bool:
    return isinstance(value, str) and bool(_WELL_FORMED_MONEY_RE.fullmatch(value))


def _is_trustworthy_quantity(value: Any) -> bool:
    return isinstance(value, str) and value.isdigit() and 1 <= int(value) <= 99


# Safety net for ONE specific, narrow PP-Structure failure mode: the Amount cell is
# genuinely missing (never read at all) while Basic and Quantity both came through
# clean and well-formed. Since Amount = Basic x Quantity is a printed-form invariant on
# this template, a missing Amount can be safely derived from the two that WERE read.
#
# Deliberately does NOT touch a row where Amount already holds a value, however
# malformed-looking - a present value is evidence something real was printed there, and
# there is no reliable way to tell whether Basic, Quantity, or Amount is the one that's
# actually wrong. Overwriting a present Amount from Basic x Quantity was tried and found
# unsafe: on a real sample where Quantity itself had been misread, it replaced an
# already-correct (if oddly-formatted) Amount with a wrong one computed from the bad
# Quantity - amplifying one field's error into another's data instead of fixing it.
def _apply_row_arithmetic_repair(item: dict[str, Any]) -> dict[str, Any]:
    if item.get("amount") is not None:
        return item
    if not _is_trustworthy_money(item.get("basic")):
        return item
    if not _is_trustworthy_quantity(item.get("quantity")):
        return item

    basic = _parse_money(item["basic"])
    quantity = int(item["quantity"])
    assert basic is not None  # _is_trustworthy_money already guarantees this parses

    return {
        **item,
        "amount": _format_money(round(basic * quantity, 2)),
        "amountConfidence": CONFIDENCE_CORRECTED,
        "amountAutoCorrected": True,
    }


# Safety net for the Total Basic Amount summary cell: on this template it always equals
# the sum of every line item's Amount column. Only recomputes it when every single line
# item's Amount is well-formed money (see _is_trustworthy_money) - a merely "confidently
# formatted" value isn't enough basis, since a well-formatted Quantity/Basic pair can
# still combine into a wrong-but-clean-looking Amount (a genuinely misread Quantity, for
# example) - requiring every summand itself look exactly as printed on this template is
# the only cross-check cheap enough to trust here without inventing anything.
def _apply_tba_cross_check(summary: dict[str, Any], items: list[dict[str, Any]]) -> dict[str, Any]:
    if not items:
        return summary
    amounts: list[float] = []
    for item in items:
        if not _is_trustworthy_money(item.get("amount")):
            return summary  # at least one row's amount isn't trustworthy - don't guess
        parsed = _parse_money(item["amount"])
        assert parsed is not None  # _is_trustworthy_money already guarantees this parses
        amounts.append(parsed)

    computed_tba = round(sum(amounts), 2)
    current_tba = _parse_money(summary.get("totalBasicAmount"))
    if current_tba is not None and abs(current_tba - computed_tba) < 0.01:
        return summary  # already consistent

    return {
        **summary,
        "totalBasicAmount": _format_money(computed_tba),
        "totalBasicAmountConfidence": CONFIDENCE_CORRECTED,
        "totalBasicAmountAutoCorrected": True,
    }


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
    raw_part1 = _apply_po_request_swap_safety_net(raw_part1)
    raw_part2 = await process_part2(part2_bytes, part2_mime)

    update: dict[str, Any] = _apply_corrections(raw_part1, PART1_FIELD_CLASSES)
    update.update(_apply_pincode_correction("consignee", raw_part1.get("consigneeAddress")))
    update.update(_apply_pincode_correction("consignor", raw_part1.get("consignorAddress")))

    line_items = _apply_line_item_corrections(raw_part2.get("lineItems", []))
    update["lineItems"] = [_apply_row_arithmetic_repair(item) for item in line_items]
    summary = _apply_corrections(raw_part2, PART2_SUMMARY_FIELD_CLASSES)
    update.update(_apply_tba_cross_check(summary, update["lineItems"]))
    update["multiPage"] = bool(raw_part2.get("multiPage", False))

    line_item_confidences = {
        f"lineItem{i}.{k}": v for i, item in enumerate(update["lineItems"]) for k, v in item.items()
    }
    update["hasLowConfidenceFields"] = _has_low_confidence(update) or _has_low_confidence(
        line_item_confidences
    )

    return update
