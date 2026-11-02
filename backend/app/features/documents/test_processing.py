from typing import Any

import pytest

from app.features.documents.processing import (
    _apply_corrections,
    _apply_pincode_correction,
    _has_low_confidence,
    _min_confidence,
)
from app.features.ocr.extraction import PART1_FIELD_CLASSES


def test_apply_corrections_produces_confidence_and_flag_per_field() -> None:
    raw = {"consigneeCode": "341198", "consignee": "OERLIKON BALZERS COATING INDIA"}
    result = _apply_corrections(raw, PART1_FIELD_CLASSES)
    assert result["consigneeCode"] == "341198"
    assert result["consigneeCodeConfidence"] == 100
    assert result["consigneeCodeAutoCorrected"] is False


def test_apply_corrections_handles_missing_field_as_null() -> None:
    result = _apply_corrections({}, PART1_FIELD_CLASSES)
    assert result["invoiceNo"] is None
    assert result["invoiceNoConfidence"] == 0


def test_apply_pincode_correction_extracts_from_address() -> None:
    result = _apply_pincode_correction("consignee", "AHMEDABAD\n382220")
    assert result["consigneePincode"] == "382220"
    assert result["consigneePincodeConfidence"] == 100


def test_apply_pincode_correction_null_when_no_address() -> None:
    result = _apply_pincode_correction("consignee", None)
    assert result["consigneePincode"] is None


def test_has_low_confidence_true_when_any_field_below_threshold() -> None:
    fields = {"aConfidence": 100, "bConfidence": 40, "notAConfidenceField": 5}
    assert _has_low_confidence(fields) is True


def test_has_low_confidence_false_when_all_above_threshold() -> None:
    fields = {"aConfidence": 100, "bConfidence": 90}
    assert _has_low_confidence(fields) is False


def test_plain_free_text_confidence_70_is_not_low() -> None:
    assert _has_low_confidence({"reasonConfidence": 70, "consigneeAddressConfidence": 70}) is False


def test_auto_corrected_55_and_doubtful_20_are_low() -> None:
    assert _has_low_confidence({"aConfidence": 100, "bConfidence": 55}) is True
    assert _has_low_confidence({"aConfidence": 100, "bConfidence": 20}) is True
    assert _has_low_confidence({"aConfidence": 60}) is False  # the threshold itself is fine


def test_line_item_confidence_55_is_low() -> None:
    assert _has_low_confidence({"lineItem0.amountConfidence": 55}) is True
    assert _has_low_confidence({"lineItem0.descriptionConfidence": 70}) is False


def test_min_confidence_picks_lowest_of_mixed_values() -> None:
    fields = {"aConfidence": 100, "bConfidence": 40, "notAConfidenceField": 5}
    assert _min_confidence(fields) == 40


def test_min_confidence_all_high_returns_the_lowest_high_value() -> None:
    fields = {"aConfidence": 95, "bConfidence": 90}
    assert _min_confidence(fields) == 90


def test_min_confidence_all_low_returns_the_lowest_value() -> None:
    fields = {"aConfidence": 40, "bConfidence": 10}
    assert _min_confidence(fields) == 10


def test_min_confidence_empty_dict_returns_none() -> None:
    assert _min_confidence({}) is None


def test_min_confidence_no_confidence_keys_returns_none() -> None:
    assert _min_confidence({"invoiceNo": "123", "consignee": "ACME"}) is None


def test_format_net_moves_values_to_the_field_their_shape_belongs_to() -> None:
    from app.features.documents.processing import _apply_format_reassignment_safety_net as net

    out = net(
        {
            "consignorPoNo": "0000166771",
            "requestNo": "AABCE9378F",
            "consignorPan": "23AABCE9378F3ZI",
            "consignorGstin": "3242064440",
        }
    )
    assert out["consignorPoNo"] == "3242064440"
    assert out["requestNo"] == "0000166771"
    assert out["consignorPan"] == "AABCE9378F"
    assert out["consignorGstin"] is None or out["consignorGstin"] != "3242064440"


def test_format_net_leaves_correct_and_missing_values_alone() -> None:
    from app.features.documents.processing import _apply_format_reassignment_safety_net as net

    good = {
        "consignorPoNo": "3242064440",
        "requestNo": "0000166771",
        "consignorPan": "AABCE9378F",
        "consignorGstin": None,
    }
    assert net(good) == good


# ------------------------------------------------- document-level flag: Sr No never counts
def _raw_part1() -> dict[str, Any]:
    return {
        "consigneeCode": "1001",
        "consignee": "ACME TRADERS",
        "consigneeAddress": "12 Main Road Pune 411001",
        "consigneeStateCode": "27",
        "consigneeStateName": "MAHARASHTRA",
        "consigneeGstin": "27AABCU9603R1ZM",
        "consigneePan": "AABCU9603R",
        "invoiceNo": "S5001234567",
        "fiDoc": "1900001234",
        "challanDate": "01.07.26",
        "reason": "Sample return",
        "consignorName": "GLOBAL SUPPLIES",
        "consignorAddress": "5 Industrial Estate Mumbai 400001",
        "consignorStateCode": "27",
        "consignorStateName": "MAHARASHTRA",
        "consignorPoNo": "4500001234",
        "consignorGstin": "27AABCU9603R1ZM",
        "consignorPan": "AABCU9603R",
        "requestNo": "7000001234",
        "irnNo": None,
    }


def _raw_item(sr: str | None = "1") -> dict[str, Any]:
    return {
        "srNo": sr,
        "description": "Bolt M8",
        "hsnSac": "7318",
        "basic": "100.00",
        "quantity": "2",
        "amount": "200.00",
    }


def _raw_part2(items: list[dict[str, Any]]) -> dict[str, Any]:
    basic = sum(
        float(i["amount"].replace(",", "").replace("O", "0")) for i in items if i.get("amount")
    )
    # the printed total must equal the row sum, or the TBA cross-check rewrites it (55)
    return {
        "lineItems": items,
        "cgstRate": "9.00",
        "cgstAmount": "18.00",
        "sgstRate": "9.00",
        "sgstAmount": "18.00",
        "igstRate": "0.00",
        "igstAmount": "0.00",
        "totalBasicAmount": f"{basic:,.2f}",
        "totalAmount": f"{basic * 1.18:,.2f}",
        "multiPage": False,
    }


async def _run(monkeypatch: pytest.MonkeyPatch, items: list[dict[str, Any]]) -> dict[str, Any]:
    from app.features.documents import processing

    async def part1(*_: Any) -> dict[str, Any]:
        return _raw_part1()

    async def part2(*_: Any) -> dict[str, Any]:
        return _raw_part2(items)

    monkeypatch.setattr(processing, "process_part1", part1)
    monkeypatch.setattr(processing, "process_part2", part2)
    return await processing.run_full_pipeline(b"a", "image/jpeg", b"b", "image/jpeg")


async def test_exact_fields_with_every_srno_unread_are_not_flagged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    out = await _run(monkeypatch, [_raw_item(None), _raw_item(None)])
    assert out["hasLowConfidenceFields"] is False
    assert out["minConfidence"] not in (0, None)
    assert out["lineItems"][0]["srNoConfidence"] == 0  # the cell itself keeps its confidence


async def test_srno_with_a_stray_character_is_not_flagged(monkeypatch: pytest.MonkeyPatch) -> None:
    out = await _run(monkeypatch, [_raw_item("1|x"), _raw_item("2")])
    assert out["lineItems"][0]["srNoConfidence"] == 20
    assert out["hasLowConfidenceFields"] is False


async def test_a_repaired_amount_is_still_flagged(monkeypatch: pytest.MonkeyPatch) -> None:
    item = _raw_item(None)
    item["amount"] = "2OO.00"  # letter O repaired to zero -> confidence 55
    out = await _run(monkeypatch, [item])
    assert out["lineItems"][0]["amountConfidence"] == 55
    assert out["hasLowConfidenceFields"] is True


async def test_an_empty_quantity_is_still_flagged(monkeypatch: pytest.MonkeyPatch) -> None:
    item = _raw_item(None)
    item["quantity"] = None
    item["amount"] = "200.00"
    out = await _run(monkeypatch, [item])
    assert out["lineItems"][0]["quantityConfidence"] == 0
    assert out["hasLowConfidenceFields"] is True


def test_line_item_confidences_skip_srno_only() -> None:
    from app.features.documents.processing import _line_item_confidences

    got = _line_item_confidences([{"srNoConfidence": 0, "amountConfidence": 55, "srNo": None}])
    assert "lineItem0.srNoConfidence" not in got
    assert got["lineItem0.amountConfidence"] == 55
