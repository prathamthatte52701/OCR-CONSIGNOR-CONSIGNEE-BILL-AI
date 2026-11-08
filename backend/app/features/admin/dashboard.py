"""Dashboard extras for GET /admin/telemetry: daily series, 7-day trends and the grouped recent
activity feed (ported from ACKN). Counts only, never document or message text; the feed carries
action names, times and usernames, never an audit row's raw context."""

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
SERIES_DAYS = 14
FEED_SIZE = 10
FEED_FETCH = 60  # raw events read to build FEED_SIZE grouped items
FEED_GROUP_WINDOW = timedelta(minutes=10)
# Audit noise, not dashboard news.
FEED_HIDDEN_ACTIONS = ["admin_access"]


async def gather_untyped(*aws: Any) -> list[Any]:
    """asyncio.gather, typed loosely: its overloads stop at 6 awaitables."""
    return list(await asyncio.gather(*aws))


def series_days(now: datetime | None = None) -> list[str]:
    """The last SERIES_DAYS IST calendar days, oldest first, as YYYY-MM-DD."""
    today = (now or datetime.now(UTC)).astimezone(IST).date()
    return [(today - timedelta(days=i)).isoformat() for i in range(SERIES_DAYS - 1, -1, -1)]


def _day_start_utc(day: str) -> datetime:
    return datetime.fromisoformat(day).replace(tzinfo=IST).astimezone(UTC)


async def daily_counts(
    db: Any, collection: str, field: str, days: list[str], extra: dict[str, Any] | None = None
) -> list[int]:
    """Per-IST-day counts for the given days; a day with nothing is 0."""
    coll = db[collection]

    def count(day: str) -> Any:
        start = _day_start_utc(day)
        return coll.count_documents(
            {**(extra or {}), field: {"$gte": start, "$lt": start + timedelta(days=1)}}
        )

    return list(await asyncio.gather(*(count(d) for d in days)))


async def trend(
    db: Any, collection: str, field: str, extra: dict[str, Any] | None = None
) -> dict[str, int]:
    """Last 7 days against the 7 days before them (rolling windows)."""
    now = datetime.now(UTC)
    week, two_weeks = now - timedelta(days=7), now - timedelta(days=14)
    base = extra or {}
    cur, prev = await asyncio.gather(
        db[collection].count_documents({**base, field: {"$gte": week}}),
        db[collection].count_documents({**base, field: {"$gte": two_weeks, "$lt": week}}),
    )
    return {"current": cur, "previous": prev}


def feed_items(
    events: list[dict[str, Any]], names: dict[Any, dict[str, Any]]
) -> list[dict[str, Any]]:
    """Newest-first audit events -> at most FEED_SIZE items. Consecutive identical actions by the
    same user within FEED_GROUP_WINDOW collapse into one item with a count."""
    items: list[dict[str, Any]] = []
    for ev in events:
        uid = ev.get("userId")
        when = ev.get("createdAt")
        last = items[-1] if items else None
        if (
            last is not None
            and last["_uid"] == uid
            and last["action"] == ev.get("action")
            and isinstance(when, datetime)
            and isinstance(last["_oldest"], datetime)
            and last["_oldest"] - when <= FEED_GROUP_WINDOW
        ):
            last["count"] += 1
            last["_oldest"] = when
            continue
        if len(items) >= FEED_SIZE:
            break
        owner = names.get(uid)
        items.append(
            {
                "id": str(ev["_id"]),
                "action": str(ev.get("action", "")),
                "createdAt": when,
                "user": {"id": str(owner["_id"]), "username": owner["username"]} if owner else None,
                "count": 1,
                "_uid": uid,
                "_oldest": when,
            }
        )
    for it in items:
        it.pop("_uid", None)
        it.pop("_oldest", None)
    return items


async def recent_feed(db: Any) -> list[dict[str, Any]]:
    events = (
        await db.auditlogs.find({"action": {"$nin": FEED_HIDDEN_ACTIONS}})
        .sort("createdAt", -1)
        .limit(FEED_FETCH)
        .to_list(FEED_FETCH)
    )
    ids = list({e["userId"] for e in events if e.get("userId")})
    names = {u["_id"]: u async for u in db.users.find({"_id": {"$in": ids}}, {"username": 1})}
    return feed_items(events, names)
