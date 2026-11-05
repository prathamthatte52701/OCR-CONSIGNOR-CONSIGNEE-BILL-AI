"""Query building for the document list (GET /documents): free-text search, challan-date and
month filters, IST upload ranges, needs-review and the server-side sort pipeline.

challanDate is OCR'd printed text: day-first, separators . / -, 1 or 2 digit day and month,
2 or 4 digit year (01/07/2026, 01.07.26, 1-7-2026). The date filters therefore use tolerant
regexes, and the sort normalises the text to YYYYMMDD inside an aggregation."""

import re
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from pymongo.collation import Collation

IST = ZoneInfo("Asia/Kolkata")

MAX_SEARCH_LENGTH = 100
SORT_FIELDS = (
    "invoiceNo",
    "consigneeCode",
    "consignee",
    "challanDate",
    "uploadStatus",
    "createdAt",
)
TEXT_COLLATION = Collation(locale="en", strength=2)  # case-insensitive text sort
SORT_HELPER = "_sortKey"

_SEP = r"[./-]"
_YEAR_ANY = r"(?:\d{4}|\d{2})"
_MONTH_RE = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$")
_DATE_PARAM_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
# Any string that is NOT date-shaped (used for the "No date found" month filter).
_NOT_DATE_SHAPED = rf"^(?!\s*\d{{1,2}}{_SEP}\d{{1,2}}{_SEP}{_YEAR_ANY}\s*$)"


def _bad(detail: str) -> HTTPException:
    return HTTPException(status_code=400, detail=detail)


def _search_condition(search: str) -> dict[str, Any]:
    text = search.strip()
    if "\x00" in search:
        raise _bad("Invalid search text.")
    if len(text) > MAX_SEARCH_LENGTH:
        raise _bad(f"Search text must be at most {MAX_SEARCH_LENGTH} characters.")
    regex = {"$regex": re.escape(text), "$options": "i"}
    return {"$or": [{"invoiceNo": regex}, {"consigneeCode": regex}, {"consignee": regex}]}


def _date_condition(day: str) -> dict[str, Any]:
    if not _DATE_PARAM_RE.fullmatch(day):
        raise _bad("Invalid date. Use YYYY-MM-DD.")
    try:
        picked = date.fromisoformat(day)
    except ValueError:
        raise _bad("Invalid date. Use YYYY-MM-DD.") from None
    year = rf"(?:{picked.year}|{str(picked.year)[2:]})"
    pattern = rf"^\s*0?{picked.day}{_SEP}0?{picked.month}{_SEP}{year}\s*$"
    return {"challanDate": {"$regex": pattern}}


def _month_condition(month: str) -> dict[str, Any]:
    if month == "none":
        return {
            "$or": [
                {"challanDate": None},  # missing or null
                {"challanDate": {"$regex": _NOT_DATE_SHAPED}},  # empty or not date-shaped
            ]
        }
    m = _MONTH_RE.match(month)
    if not m:
        raise _bad("Invalid month. Use YYYY-MM or none.")
    year, mm = m.group(1), int(m.group(2))
    pattern = rf"^\s*\d{{1,2}}{_SEP}0?{mm}{_SEP}(?:{year}|{year[2:]})\s*$"
    return {"challanDate": {"$regex": pattern}}


def upload_range_start_utc(range_key: str, now: datetime) -> datetime:
    """Start of the IST calendar bucket (today / Monday-week / month / year) containing `now`,
    as a UTC instant. `now` must be tz-aware. Open-ended $gte is enough: createdAt is never in
    the future of the instant the query runs."""
    start = now.astimezone(IST).replace(hour=0, minute=0, second=0, microsecond=0)
    if range_key == "week":
        start -= timedelta(days=start.weekday())  # Monday == weekday() 0
    elif range_key == "month":
        start = start.replace(day=1)
    elif range_key == "year":
        start = start.replace(month=1, day=1)
    elif range_key != "today":
        raise ValueError(f"Unknown range: {range_key}")  # unreachable - Query() pattern checks
    return start.astimezone(UTC)


def build_list_query(
    user_id: Any,
    *,
    search: str | None = None,
    day: str | None = None,
    month: str | None = None,
    date_range: str | None = None,
    needs_review: bool = False,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Every condition is collected and combined with $and, so the search $or, the month "none"
    $or and the needs-review $or can never overwrite each other."""
    if day and month:
        raise _bad("Use either a date or a month, not both.")
    conditions: list[dict[str, Any]] = []
    if search and search.strip():
        conditions.append(_search_condition(search))
    if day:
        conditions.append(_date_condition(day))
    if month:
        conditions.append(_month_condition(month))
    if date_range:
        start = upload_range_start_utc(date_range, now or datetime.now(UTC))
        conditions.append({"createdAt": {"$gte": start}})
    if needs_review:
        conditions.append(
            {
                "$or": [
                    {"uploadStatus": "failed"},
                    {"hasLowConfidenceFields": True},
                    {"hasReviewWarnings": True},
                ]
            }
        )
    query: dict[str, Any] = {"userId": user_id, "isDeleted": {"$ne": True}}
    if conditions:
        query["$and"] = conditions
    return query


def _str_or_empty(field: str) -> dict[str, Any]:
    return {"$cond": [{"$eq": [{"$type": field}, "string"]}, field, ""]}


def _pad2(value: dict[str, Any]) -> dict[str, Any]:
    return {"$cond": [{"$eq": [{"$strLenCP": value}, 1]}, {"$concat": ["0", value]}, value]}


def _challan_date_key() -> dict[str, Any]:
    """challanDate text -> YYYYMMDD ('' when missing or not date-shaped)."""
    regex = rf"^\s*(\d{{1,2}}){_SEP}(\d{{1,2}}){_SEP}({_YEAR_ANY})\s*$"

    def capture(index: int) -> dict[str, Any]:
        return {"$arrayElemAt": ["$$m.captures", index]}

    year = {
        "$cond": [
            {"$eq": [{"$strLenCP": capture(2)}, 2]},
            {"$concat": ["20", capture(2)]},
            capture(2),
        ]
    }
    return {
        "$cond": [
            {"$eq": [{"$type": "$challanDate"}, "string"]},
            {
                "$let": {
                    "vars": {"m": {"$regexFind": {"input": "$challanDate", "regex": regex}}},
                    "in": {
                        "$cond": [
                            {"$eq": ["$$m", None]},
                            "",
                            {"$concat": [year, _pad2(capture(1)), _pad2(capture(0))]},
                        ]
                    },
                }
            },
            "",
        ]
    }


def sort_key_expr(sort: str) -> Any:
    if sort == "challanDate":
        return _challan_date_key()
    if sort == "createdAt":
        return "$createdAt"
    return _str_or_empty(f"${sort}")


def sorted_page_pipeline(
    match: dict[str, Any], sort: str, direction: int, skip: int, limit: int
) -> list[dict[str, Any]]:
    """`_id` is the final tie-breaker in the SAME direction, so walking every page yields each
    document exactly once."""
    return [
        {"$match": match},
        {"$addFields": {SORT_HELPER: sort_key_expr(sort)}},
        {"$sort": {SORT_HELPER: direction, "_id": direction}},
        {"$skip": skip},
        {"$limit": limit},
        {"$project": {SORT_HELPER: 0}},
    ]
