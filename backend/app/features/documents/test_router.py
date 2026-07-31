from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from app.features.documents.router import ist_today_utc_range

IST = ZoneInfo("Asia/Kolkata")


def test_ist_today_range_covers_midday_ist() -> None:
    # 2026-01-15 12:00 IST is well inside its own IST calendar day.
    now_ist = datetime(2026, 1, 15, 12, 0, tzinfo=IST)
    start, end = ist_today_utc_range(now_ist)
    assert start <= now_ist.astimezone(UTC) < end


def test_ist_today_range_is_exactly_24_hours() -> None:
    now_ist = datetime(2026, 1, 15, 9, 30, tzinfo=IST)
    start, end = ist_today_utc_range(now_ist)
    assert (end - start).total_seconds() == 24 * 3600


def test_ist_midnight_boundary_not_shared_with_previous_utc_day() -> None:
    # 00:30 IST on 2026-01-15 is 19:00 UTC on 2026-01-14 - a naive UTC-day query would
    # miss this instant entirely; the IST-aware range must still include it.
    now_ist = datetime(2026, 1, 15, 0, 30, tzinfo=IST)
    start, end = ist_today_utc_range(now_ist)
    instant_utc = now_ist.astimezone(UTC)
    assert start <= instant_utc < end
    assert instant_utc.date() == datetime(2026, 1, 14).date()  # confirms the UTC-day mismatch
