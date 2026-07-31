from app.features.ocr.extraction import (
    FieldClass,
    correct_all_digits,
    correct_date,
    correct_field,
    correct_gstin,
    correct_invoice_no,
    correct_letters_only,
    correct_money,
    correct_pan,
    extract_pincode,
)


def test_all_digits_valid_untouched() -> None:
    result = correct_all_digits("341198")
    assert result.value == "341198"
    assert result.confidence == 100
    assert result.auto_corrected is False


def test_all_digits_corrects_confusable_chars() -> None:
    result = correct_all_digits("34ll98")  # l -> 1
    assert result.value == "341198"
    assert result.auto_corrected is True
    assert result.confidence < 100


def test_all_digits_uncorrectable_stays_low_confidence() -> None:
    result = correct_all_digits("34#198")
    assert result.value == "34#198"  # left alone, never guessed
    assert result.auto_corrected is False
    assert result.confidence < 50


def test_all_digits_empty_is_not_nullable_by_default() -> None:
    result = correct_all_digits(None)
    assert result.value is None
    assert result.confidence == 0


def test_nullable_digits_blank_is_not_a_failure() -> None:
    result = correct_field(None, FieldClass.NULLABLE_DIGITS)
    assert result.value is None
    assert result.confidence == 100  # blank IRN No is expected, not a defect


def test_letters_only_never_gets_digit_correction() -> None:
    # A name field should never have digit-confusion correction applied.
    result = correct_letters_only("OERLIKON BALZERS COATING INDIA")
    assert result.value == "OERLIKON BALZERS COATING INDIA"
    assert result.confidence == 100
    assert result.auto_corrected is False


def test_letters_only_with_bad_chars_stays_uncorrected() -> None:
    result = correct_letters_only("VE Commercial 5ehicles")  # nonsense - left alone
    assert result.auto_corrected is False


def test_gstin_valid_untouched() -> None:
    result = correct_gstin("24AAACI3916N1ZI")
    assert result.value == "24AAACI3916N1ZI"
    assert result.confidence == 100
    assert result.auto_corrected is False


def test_gstin_corrects_digit_position() -> None:
    # First 2 chars should be digits (state code); 'O' -> '0'.
    result = correct_gstin("2OAAACI3916N1ZI")
    assert result.value == "20AAACI3916N1ZI"
    assert result.auto_corrected is True


def test_gstin_anchor_z_never_corrected() -> None:
    # Position 13 must be literal 'Z' - if it's wrong, correction must not force it.
    bad = "24AAACI3916N1XI"  # position 13 is 'X', not a confusable char -> stays invalid
    result = correct_gstin(bad)
    assert result.auto_corrected is False
    assert result.confidence < 100


def test_pan_valid_untouched() -> None:
    result = correct_pan("AABCE9378F")
    assert result.value == "AABCE9378F"
    assert result.confidence == 100


def test_pan_corrects_letter_position_real_sample_case() -> None:
    # Real OCR output from a Part1 sample: 'I' misread as '1' in the letter run.
    result = correct_pan("AAAC13916N")
    assert result.value == "AAACI3916N"
    assert result.auto_corrected is True


def test_invoice_no_valid_untouched() -> None:
    result = correct_invoice_no("M13610202307")
    assert result.value == "M13610202307"
    assert result.confidence == 100


def test_invoice_no_prefix_letter_never_touched() -> None:
    # The leading letter is an anchor - correction only touches the digit run after it.
    result = correct_invoice_no("Ml3610202307")  # 'l' inside digit run -> '1'
    assert result.value == "M13610202307"
    assert result.auto_corrected is True


def test_date_valid_untouched() -> None:
    result = correct_date("04/07/26")
    assert result.value == "04/07/26"
    assert result.confidence == 100


def test_date_corrects_and_preserves_separators() -> None:
    result = correct_date("O4/07/26")  # 'O' -> '0'
    assert result.value == "04/07/26"
    assert result.auto_corrected is True


def test_money_valid_untouched() -> None:
    result = correct_money("1234.50")
    assert result.value == "1234.50"
    assert result.confidence == 100


def test_pincode_extracted_from_address() -> None:
    assert extract_pincode("AHMEDABAD\n382220") == "382220"
    assert extract_pincode("87A Industrial Area No 3\nA.B Road Dewas\n455001") == "455001"


def test_pincode_none_when_absent() -> None:
    assert extract_pincode("No pincode here") is None
    assert extract_pincode(None) is None


def test_correct_field_dispatches_by_class() -> None:
    result = correct_field("341198", FieldClass.ALL_DIGITS)
    assert result.value == "341198"
