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
