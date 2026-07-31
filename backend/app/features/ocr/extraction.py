"""Deterministic, pure-Python post-processing: corrects classic OCR character-confusion
errors based on each field's expected format. A correction is applied ONLY if it makes the
value fully valid for that field's format - otherwise it is discarded and the field is left
as-is with a low confidence score. Never guesses a value.
"""

import re
from dataclasses import dataclass
from enum import StrEnum

# Confusable-character maps, keyed by the direction of correction.
DIGIT_CONFUSION = {
    "I": "1",
    "l": "1",
    "O": "0",
    "o": "0",
    "Z": "2",
    "z": "2",
    "S": "5",
    "s": "5",
    "B": "8",
    "b": "8",
    "G": "6",
    "g": "6",
    "D": "0",
    "d": "0",
}
LETTER_CONFUSION = {"1": "I", "0": "O", "2": "Z", "5": "S", "8": "B", "6": "G"}

GSTIN_RE = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")
PAN_RE = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$")
# All confirmed real samples use a single-letter prefix (e.g. "M13610202307") - narrower
# than the originally-assumed 1-3 letter prefix, resolved by direct sample inspection.
INVOICE_NO_RE = re.compile(r"^[A-Z]\d+$")
DATE_RE = re.compile(r"^\d{2}[./-]\d{2}[./-]\d{2}$")
MONEY_RE = re.compile(r"^[\d,]+(\.\d+)?$")
PINCODE_RE = re.compile(r"\b(\d{6})\b")

# Confidence tiers.
CONFIDENCE_EXACT = 100
CONFIDENCE_CORRECTED = 55
CONFIDENCE_PLAUSIBLE = 20
CONFIDENCE_EMPTY = 0
CONFIDENCE_FREE_TEXT = 70


class FieldClass(StrEnum):
    ALL_DIGITS = "all_digits"
    NULLABLE_DIGITS = "nullable_digits"
    LETTERS_ONLY = "letters_only"
    GSTIN = "gstin"
    PAN = "pan"
    INVOICE_NO = "invoice_no"
    DATE = "date"
    FREE_TEXT_LIGHT = "free_text_light"
    MONEY = "money"


@dataclass
class CorrectionResult:
    value: str | None
    confidence: int
    auto_corrected: bool


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = " ".join(value.split())
    return stripped or None


def correct_all_digits(value: str | None, *, nullable: bool = False) -> CorrectionResult:
    cleaned = _clean(value)
    if cleaned is None:
        confidence = CONFIDENCE_EXACT if nullable else CONFIDENCE_EMPTY
        return CorrectionResult(None, confidence, False)

    if cleaned.isdigit():
        return CorrectionResult(cleaned, CONFIDENCE_EXACT, False)

    corrected = "".join(DIGIT_CONFUSION.get(c, c) for c in cleaned)
    if corrected.isdigit():
        return CorrectionResult(corrected, CONFIDENCE_CORRECTED, True)

    return CorrectionResult(cleaned, CONFIDENCE_PLAUSIBLE, False)


def correct_letters_only(value: str | None) -> CorrectionResult:
    cleaned = _clean(value)
    if cleaned is None:
        return CorrectionResult(None, CONFIDENCE_EMPTY, False)

    # Names/free text never get digit-confusion correction - there is no sensible
    # "digit target" for a proper name, so a wrong character just stays wrong-but-visible.
    if re.fullmatch(r"[A-Za-z .&'\-()]+", cleaned):
        return CorrectionResult(cleaned, CONFIDENCE_EXACT, False)
    return CorrectionResult(cleaned, CONFIDENCE_PLAUSIBLE, False)


def correct_free_text(value: str | None) -> CorrectionResult:
    cleaned = _clean(value)
    if cleaned is None:
        return CorrectionResult(None, CONFIDENCE_EMPTY, False)
    return CorrectionResult(cleaned, CONFIDENCE_FREE_TEXT, False)


def correct_gstin(value: str | None) -> CorrectionResult:
    cleaned = _clean(value)
    if cleaned is None:
        return CorrectionResult(None, CONFIDENCE_EMPTY, False)
    candidate = cleaned.upper().replace(" ", "")

    if GSTIN_RE.fullmatch(candidate):
        return CorrectionResult(candidate, CONFIDENCE_EXACT, False)
    if len(candidate) != 15:
        return CorrectionResult(cleaned, CONFIDENCE_PLAUSIBLE, False)

    chars = list(candidate)
    corrected_any = False
    digit_positions = {0, 1, 7, 8, 9, 10}
    letter_positions = {2, 3, 4, 5, 6, 11}
    for i in range(15):
        c = chars[i]
        if i in digit_positions and not c.isdigit() and c in DIGIT_CONFUSION:
            chars[i] = DIGIT_CONFUSION[c]
            corrected_any = True
        elif i in letter_positions and not c.isalpha() and c in LETTER_CONFUSION:
            chars[i] = LETTER_CONFUSION[c]
            corrected_any = True
        # i == 13 is the literal 'Z' anchor - never auto-corrected.
        # i == 12 (entity code) and i == 14 (checksum) are broad alnum - left as-is.

    corrected = "".join(chars)
    if GSTIN_RE.fullmatch(corrected):
        return CorrectionResult(corrected, CONFIDENCE_CORRECTED, corrected_any)
    return CorrectionResult(cleaned, CONFIDENCE_PLAUSIBLE, False)


def correct_pan(value: str | None) -> CorrectionResult:
    cleaned = _clean(value)
    if cleaned is None:
        return CorrectionResult(None, CONFIDENCE_EMPTY, False)
    candidate = cleaned.upper().replace(" ", "")

    if PAN_RE.fullmatch(candidate):
        return CorrectionResult(candidate, CONFIDENCE_EXACT, False)
    if len(candidate) != 10:
        return CorrectionResult(cleaned, CONFIDENCE_PLAUSIBLE, False)

    chars = list(candidate)
    corrected_any = False
    for i in range(10):
        c = chars[i]
        if i in (0, 1, 2, 3, 4, 9):
            if not c.isalpha() and c in LETTER_CONFUSION:
                chars[i] = LETTER_CONFUSION[c]
                corrected_any = True
        else:
            if not c.isdigit() and c in DIGIT_CONFUSION:
                chars[i] = DIGIT_CONFUSION[c]
                corrected_any = True

    corrected = "".join(chars)
    if PAN_RE.fullmatch(corrected):
        return CorrectionResult(corrected, CONFIDENCE_CORRECTED, corrected_any)
    return CorrectionResult(cleaned, CONFIDENCE_PLAUSIBLE, False)


def correct_invoice_no(value: str | None) -> CorrectionResult:
    cleaned = _clean(value)
    if cleaned is None:
        return CorrectionResult(None, CONFIDENCE_EMPTY, False)
    # Case is preserved here (not upper()'d yet) because DIGIT_CONFUSION distinguishes
    # lowercase 'l' (a likely '1' misread) from uppercase 'L' (a real letter).
    candidate = cleaned.replace(" ", "")

    if INVOICE_NO_RE.fullmatch(candidate.upper()):
        return CorrectionResult(candidate.upper(), CONFIDENCE_EXACT, False)

    prefix_match = re.match(r"^([A-Za-z])(.*)$", candidate)
    if prefix_match is None:
        return CorrectionResult(cleaned, CONFIDENCE_PLAUSIBLE, False)

    prefix, rest = prefix_match.groups()
    corrected_rest = "".join(DIGIT_CONFUSION.get(c, c) for c in rest)
    corrected = (prefix + corrected_rest).upper()
    if INVOICE_NO_RE.fullmatch(corrected):
        was_corrected = corrected_rest != rest
        confidence = CONFIDENCE_CORRECTED if was_corrected else CONFIDENCE_EXACT
        return CorrectionResult(corrected, confidence, was_corrected)
    return CorrectionResult(cleaned, CONFIDENCE_PLAUSIBLE, False)


def correct_date(value: str | None) -> CorrectionResult:
    cleaned = _clean(value)
    if cleaned is None:
        return CorrectionResult(None, CONFIDENCE_EMPTY, False)

    if DATE_RE.fullmatch(cleaned):
        return CorrectionResult(cleaned, CONFIDENCE_EXACT, False)

    corrected = "".join(c if c in "./-" else DIGIT_CONFUSION.get(c, c) for c in cleaned)
    if DATE_RE.fullmatch(corrected):
        return CorrectionResult(corrected, CONFIDENCE_CORRECTED, True)
    return CorrectionResult(cleaned, CONFIDENCE_PLAUSIBLE, False)


def correct_money(value: str | None) -> CorrectionResult:
    cleaned = _clean(value)
    if cleaned is None:
        return CorrectionResult(None, CONFIDENCE_EMPTY, False)

    if MONEY_RE.fullmatch(cleaned):
        return CorrectionResult(cleaned, CONFIDENCE_EXACT, False)

    corrected = "".join(c if c in ",." else DIGIT_CONFUSION.get(c, c) for c in cleaned)
    if MONEY_RE.fullmatch(corrected):
        return CorrectionResult(corrected, CONFIDENCE_CORRECTED, True)
    return CorrectionResult(cleaned, CONFIDENCE_PLAUSIBLE, False)


_CORRECTORS = {
    FieldClass.ALL_DIGITS: correct_all_digits,
    FieldClass.NULLABLE_DIGITS: lambda v: correct_all_digits(v, nullable=True),
    FieldClass.LETTERS_ONLY: correct_letters_only,
    FieldClass.GSTIN: correct_gstin,
    FieldClass.PAN: correct_pan,
    FieldClass.INVOICE_NO: correct_invoice_no,
    FieldClass.DATE: correct_date,
    FieldClass.FREE_TEXT_LIGHT: correct_free_text,
    FieldClass.MONEY: correct_money,
}


def correct_field(value: str | None, field_class: FieldClass) -> CorrectionResult:
    return _CORRECTORS[field_class](value)


def extract_pincode(address: str | None) -> str | None:
    if not address:
        return None
    match = PINCODE_RE.search(address)
    return match.group(1) if match else None


# Part 1 field -> FieldClass, per the confirmed sample-derived spec.
PART1_FIELD_CLASSES: dict[str, FieldClass] = {
    "consigneeCode": FieldClass.ALL_DIGITS,
    "consignee": FieldClass.LETTERS_ONLY,
    # Address is compound (letters + a legitimate trailing pincode), not pure letters - it
    # is stored as free text and the pincode is separately extracted/corrected as its own
    # field (see extract_pincode below), matching the spec's compound-field handling.
    "consigneeAddress": FieldClass.FREE_TEXT_LIGHT,
    "consigneeStateCode": FieldClass.ALL_DIGITS,
    "consigneeStateName": FieldClass.LETTERS_ONLY,
    "consigneeGstin": FieldClass.GSTIN,
    "consigneePan": FieldClass.PAN,
    "invoiceNo": FieldClass.INVOICE_NO,
    "fiDoc": FieldClass.ALL_DIGITS,
    "challanDate": FieldClass.DATE,
    "reason": FieldClass.FREE_TEXT_LIGHT,
    "consignorName": FieldClass.LETTERS_ONLY,
    "consignorAddress": FieldClass.FREE_TEXT_LIGHT,
    "consignorStateCode": FieldClass.ALL_DIGITS,
    "consignorStateName": FieldClass.LETTERS_ONLY,
    "consignorPoNo": FieldClass.ALL_DIGITS,
    "consignorGstin": FieldClass.GSTIN,
    "consignorPan": FieldClass.PAN,
    "requestNo": FieldClass.ALL_DIGITS,
    "irnNo": FieldClass.NULLABLE_DIGITS,
}

# Part 2 line-item subfield -> FieldClass.
LINE_ITEM_FIELD_CLASSES: dict[str, FieldClass] = {
    "srNo": FieldClass.ALL_DIGITS,
    "description": FieldClass.FREE_TEXT_LIGHT,
    "hsnSac": FieldClass.ALL_DIGITS,
    "basic": FieldClass.MONEY,
    "quantity": FieldClass.ALL_DIGITS,
    "amount": FieldClass.MONEY,
}

# Part 2 tax-summary field -> FieldClass.
PART2_SUMMARY_FIELD_CLASSES: dict[str, FieldClass] = {
    "cgstRate": FieldClass.MONEY,
    "cgstAmount": FieldClass.MONEY,
    "sgstRate": FieldClass.MONEY,
    "sgstAmount": FieldClass.MONEY,
    "igstRate": FieldClass.MONEY,
    "igstAmount": FieldClass.MONEY,
    "totalBasicAmount": FieldClass.MONEY,
    "totalAmount": FieldClass.MONEY,
}
