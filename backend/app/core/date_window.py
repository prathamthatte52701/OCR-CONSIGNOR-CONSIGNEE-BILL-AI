"""Plausibility window for a document's own printed date. Warning only: the stored value is never
changed. challanDate is day-first printed text (separators . / -, 1 or 2 digit day and month, 2 or 4
digit year; a 2-digit year means 20YY, as in the list sort)."""

import re
from datetime import date, timedelta

MAX_FUTURE_DAYS = 1
MAX_PAST_YEARS = 5

_DATE_RE = re.compile(r"^(\d{1,2})[./-](\d{1,2})[./-](\d{4}|\d{2})$")


def date_implausible(date_str: str | None, today: date) -> bool:
    """True only for a REAL date outside the window (more than MAX_FUTURE_DAYS ahead of `today`,
    more than MAX_PAST_YEARS back, or in a future year). Missing/unreadable/unreal -> False."""
    match = _DATE_RE.match(date_str.strip()) if isinstance(date_str, str) else None
    if not match:
        return False
    day, month, year = int(match.group(1)), int(match.group(2)), match.group(3)
    try:
        parsed = date(2000 + int(year) if len(year) == 2 else int(year), month, day)
    except ValueError:
        return False
    try:
        oldest = today.replace(year=today.year - MAX_PAST_YEARS)
    except ValueError:  # 29 Feb minus N years
        oldest = today.replace(year=today.year - MAX_PAST_YEARS, day=28)
    plausible = (
        oldest <= parsed <= today + timedelta(days=MAX_FUTURE_DAYS) and parsed.year <= today.year
    )
    return not plausible
