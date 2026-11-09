"""Review warnings for the detail page. Pure and computed on every read - nothing is stored, so
an edit changes them at once. Only for finished (processed) documents."""

import math
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from app.core.date_window import date_implausible
from app.features.documents.processing import _format_money, _parse_money

LINE_ITEMS_TOLERANCE = 0.01
GRAND_TOTAL_TOLERANCE = 1.00  # rupee rounding is allowed
IST = ZoneInfo("Asia/Kolkata")
# Every date field stored on a document: (key, label shown in the warning).
_DATE_FIELDS = (("challanDate", "Date"),)
_TAXES = (("cgstAmount", "cgstRate"), ("sgstAmount", "sgstRate"), ("igstAmount", "igstRate"))


def _money(value: Any) -> float | None:
    parsed = _parse_money(value)
    return parsed if parsed is not None and math.isfinite(parsed) else None


def _tax_amount(doc: dict[str, Any], amount_key: str, rate_key: str) -> float | None:
    """The tax amount; 0 when it is absent AND its rate is empty/0; None when it cannot be told."""
    amount = _money(doc.get(amount_key))
    if amount is not None:
        return amount
    rate = doc.get(rate_key)
    if rate is None or (isinstance(rate, str) and not rate.strip()):
        return 0.0
    if isinstance(rate, str) and _money(rate.strip().rstrip("%")) == 0:
        return 0.0
    return None


MAX_POSITIONS = 5
MIN_DESCRIPTION_CHARS = 3
MAX_SYMBOL_SHARE = 0.4  # symbols/broken characters over this share of the text = junk


def _positions(rows: list[int]) -> str:
    shown = ", ".join(str(n) for n in rows[:MAX_POSITIONS])
    return shown + (", ..." if len(rows) > MAX_POSITIONS else "")


def serial_warning_rows(line_items: list[Any]) -> list[int]:
    """1-based positions whose serial number is empty/non-numeric, or does not go up."""
    bad: list[int] = []
    last: int | None = None
    for pos, item in enumerate(line_items, 1):
        raw = str(item.get("srNo") if isinstance(item, dict) else "" or "").strip()
        if not raw.isdecimal():
            bad.append(pos)
            continue
        number = int(raw)
        if last is not None and number <= last:
            bad.append(pos)
        last = number
    return bad


def description_warning_rows(line_items: list[Any]) -> list[int]:
    """1-based positions whose description is empty, tiny or mostly symbols."""
    bad: list[int] = []
    for pos, item in enumerate(line_items, 1):
        text = "".join(str(item.get("description") or "").split()) if isinstance(item, dict) else ""
        symbols = sum(not ch.isalnum() for ch in text)
        if len(text) < MIN_DESCRIPTION_CHARS or symbols / len(text) > MAX_SYMBOL_SHARE:
            bad.append(pos)
    return bad


def amount_warning_rows(line_items: list[Any]) -> list[int]:
    """1-based positions where quantity x basic != amount (rows with a missing value skipped)."""
    bad: list[int] = []
    for pos, item in enumerate(line_items, 1):
        if not isinstance(item, dict):
            continue
        qty, rate, amount = (_money(item.get(k)) for k in ("quantity", "basic", "amount"))
        if qty is None or rate is None or amount is None:
            continue
        if abs(qty * rate - amount) > LINE_ITEMS_TOLERANCE:
            bad.append(pos)
    return bad


def review_warnings(doc: dict[str, Any], today: date | None = None) -> list[dict[str, str]]:
    if doc.get("uploadStatus") != "processed":
        return []
    warnings: list[dict[str, str]] = []
    today = today or datetime.now(IST).date()

    for key, label in _DATE_FIELDS:
        value = doc.get(key)
        if date_implausible(value, today):
            warnings.append(
                {
                    "code": "date_implausible",
                    "message": (
                        f"{label} looks wrong ({str(value).strip()[:20]}) - please check it "
                        "against the original."
                    ),
                }
            )

    basic = _money(doc.get("totalBasicAmount"))
    line_items = doc.get("lineItems") or []
    if basic is not None and line_items:
        amounts = [_money(item.get("amount")) for item in line_items]
        if all(a is not None for a in amounts):
            total = sum(a for a in amounts if a is not None)
            if abs(total - basic) > LINE_ITEMS_TOLERANCE:
                warnings.append(
                    {
                        "code": "line_items_total",
                        "message": (
                            f"Line items add up to {_format_money(total)} but Total Basic Amount "
                            f"is {_format_money(basic)} - a row may be missing or a value may "
                            "be wrong."
                        ),
                    }
                )

    bad_serials = serial_warning_rows(line_items)
    if bad_serials:
        warnings.append(
            {
                "code": "serial_numbers",
                "message": (
                    f"Line item {_positions(bad_serials)}: serial number looks wrong or "
                    "missing - please check it against the original."
                ),
            }
        )

    bad_descriptions = description_warning_rows(line_items)
    if bad_descriptions:
        warnings.append(
            {
                "code": "descriptions",
                "message": (
                    f"Line item {_positions(bad_descriptions)}: description is empty or "
                    "unreadable - please check it against the original."
                ),
            }
        )

    bad_amounts = amount_warning_rows(line_items)
    if bad_amounts:
        warnings.append(
            {
                "code": "row_amounts",
                "message": (
                    f"Line item {_positions(bad_amounts)}: quantity x basic does not match "
                    "amount - please check."
                ),
            }
        )

    if doc.get("totalBasicAmountAutoCorrected") is True:
        warnings.append(
            {
                "code": "tba_adjusted",
                "message": (
                    "Total Basic Amount was auto-corrected (for example recalculated from the "
                    "line items) - please check it against the original."
                ),
            }
        )

    grand = _money(doc.get("totalAmount"))
    if basic is not None and grand is not None:
        taxes = [_tax_amount(doc, amount, rate) for amount, rate in _TAXES]
        if all(t is not None for t in taxes):
            expected = basic + sum(t for t in taxes if t is not None)
            if abs(expected - grand) > GRAND_TOTAL_TOLERANCE:
                warnings.append(
                    {
                        "code": "grand_total",
                        "message": (
                            f"Total Basic Amount plus taxes is {_format_money(expected)} but "
                            f"Total Amount is {_format_money(grand)} - please check the totals "
                            "against the original."
                        ),
                    }
                )

    if doc.get("multiPage") is True:
        warnings.append(
            {
                "code": "multi_page",
                "message": (
                    "This document has more than one page. Only the uploaded page is read - "
                    "rows on other pages are missing."
                ),
            }
        )
    return warnings
