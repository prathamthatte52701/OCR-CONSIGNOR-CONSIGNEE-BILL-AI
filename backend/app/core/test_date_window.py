from datetime import date

import pytest

from app.core.date_window import date_implausible

TODAY = date(2026, 7, 10)


@pytest.mark.parametrize(
    ("value", "flagged"),
    [
        ("10/07/2026", False),  # today
        ("11/07/2026", False),  # exactly +1 day is fine
        ("12/07/2026", True),  # +2 days
        ("01/01/2027", True),  # future year
        ("10/07/2021", False),  # exactly 5 years back
        ("09/07/2021", True),  # 5 years and 1 day back
        ("10.07.26", False),  # other separators, 2-digit year
        ("5-7-2026", False),  # 1-digit day and month
        ("12-07-26", True),
        ("31/02/2026", False),  # impossible date: not flagged
        ("00/00/0000", False),
        ("", False),
        (None, False),
        ("garbage", False),
        ("2026-07-10", False),  # not a stored shape: unreadable
    ],
)
def test_date_implausible(value: str | None, flagged: bool) -> None:
    assert date_implausible(value, TODAY) is flagged


def test_29_feb_today_looks_back_five_years() -> None:
    leap = date(2028, 2, 29)
    assert date_implausible("28/02/2023", leap) is False  # clamped to 28 Feb 2023
    assert date_implausible("27/02/2023", leap) is True
    assert date_implausible("29/02/2028", leap) is False
