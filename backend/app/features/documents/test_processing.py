from app.features.documents.processing import (
    _apply_corrections,
    _apply_pincode_correction,
    _has_low_confidence,
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
