"""Feature 17: GET /admin/telemetry dashboard extras (series, trends, pending list, feed)."""

from datetime import UTC, datetime, timedelta
from typing import Any

from app.features.admin.dashboard import SERIES_DAYS, feed_items


async def get(client: Any, who: Any = None) -> Any:
    return await client.get("/api/admin/telemetry", headers=who.headers if who else {})


def doc(owner: Any, status: str = "processed", created: datetime | None = None) -> dict[str, Any]:
    return {
        "userId": owner.id,
        "uploadStatus": status,
        "createdAt": created or datetime.now(UTC),
        "processedAt": created or datetime.now(UTC),
        "consignee": "SECRET CONSIGNEE LTD",
        "invoiceNo": "M99999",
    }


async def test_admin_only(client: Any, make_user: Any) -> None:
    user = await make_user()
    assert (await get(client, user)).status_code == 403
    assert (await get(client)).status_code in (401, 403)


async def test_empty_db_shape_and_zero_filled_series(client: Any, make_user: Any) -> None:
    admin = await make_user(role="admin")
    body = (await get(client, admin)).json()
    # old fields are still there
    for key in ("totalUsers", "totalDocuments", "documentsByStatus", "ocrFailureRate"):
        assert key in body
    s = body["series"]
    assert len(s["days"]) == len(s["uploads"]) == len(s["failures"]) == SERIES_DAYS
    assert s["days"] == sorted(s["days"])
    assert s["uploads"] == [0] * SERIES_DAYS and s["failures"] == [0] * SERIES_DAYS
    assert body["trends"]["uploads"] == {"current": 0, "previous": 0}
    assert body["pendingUsers"] == {"count": 0, "oldest": []}
    assert body["failedDocuments"] == 0 and body["orphanedFiles"] == 0
    assert body["passwordRequests"] == {"count": 0}
    assert isinstance(body["activityFeed"], list)


async def test_series_trends_and_counts(client: Any, make_user: Any, db: Any) -> None:
    admin, u = await make_user(role="admin"), await make_user()
    now = datetime.now(UTC)
    await db.documents.insert_many(
        [
            doc(u),
            doc(u, "failed"),
            doc(u, "processed", now - timedelta(days=3)),
            doc(u, "failed", now - timedelta(days=10)),
            doc(u, "processed", now - timedelta(days=400)),  # outside the series
        ]
    )
    body = (await get(client, admin)).json()
    s = body["series"]
    assert s["uploads"][-1] == 2 and s["failures"][-1] == 1  # today
    assert sum(s["uploads"]) == 4 and sum(s["failures"]) == 2  # the 400-day-old one is not in it
    assert body["trends"]["uploads"] == {"current": 3, "previous": 1}
    assert body["trends"]["failures"] == {"current": 1, "previous": 1}
    assert body["processedDocuments"]["total"] == 3
    assert body["failedDocuments"] == 2


async def test_pending_list_only_pending_oldest_first_safe_fields(
    client: Any, make_user: Any, db: Any
) -> None:
    admin = await make_user(role="admin")
    await make_user(status="approved")
    await make_user(status="rejected")
    pending = [await make_user(status="pending") for _ in range(7)]
    now = datetime.now(UTC)
    for i, p in enumerate(pending):
        await db.users.update_one(
            {"_id": p.id}, {"$set": {"createdAt": now - timedelta(days=9 - i)}}
        )
    body = (await get(client, admin)).json()["pendingUsers"]
    assert body["count"] == 7 and len(body["oldest"]) == 5
    assert [x["id"] for x in body["oldest"]] == [str(p.id) for p in pending[:5]]
    assert all(set(x) == {"id", "username", "email", "createdAt"} for x in body["oldest"])
    assert "passwordHash" not in str(body)


async def test_feed_is_safe_capped_and_grouped(client: Any, make_user: Any, db: Any) -> None:
    admin = await make_user(role="admin")
    a, b = await make_user(username="alice"), await make_user(username="bobby")
    now = datetime.now(UTC)
    events = [
        {
            "userId": a.id,
            "action": "document_uploaded",
            "context": {"documentId": "x", "text": "SECRET-TEXT", "email": "leak@example.com"},
            "createdAt": now - timedelta(seconds=i),
        }
        for i in range(3)
    ]
    events.append(
        {"userId": b.id, "action": "login", "context": {}, "createdAt": now - timedelta(minutes=1)}
    )
    events.append({"userId": a.id, "action": "admin_access", "context": {}, "createdAt": now})
    events += [
        {
            "userId": b.id if i % 2 else a.id,
            "action": f"act_{i}",
            "context": {},
            "createdAt": now - timedelta(hours=1, seconds=i),
        }
        for i in range(30)
    ]
    await db.auditlogs.insert_many(events)
    res = await get(client, admin)
    feed = res.json()["activityFeed"]
    assert len(feed) == 10
    assert feed[0]["action"] == "document_uploaded" and feed[0]["count"] == 3
    assert feed[0]["user"]["username"] == "alice" and feed[1]["action"] == "login"
    assert all(i["action"] != "admin_access" for i in feed)
    assert all(set(i) == {"id", "action", "createdAt", "user", "count"} for i in feed)
    assert "SECRET-TEXT" not in res.text and "leak@example.com" not in res.text
    assert "SECRET CONSIGNEE" not in res.text


def test_feed_items_handles_removed_users() -> None:
    ev = {"_id": 1, "userId": None, "action": "signup", "createdAt": datetime.now(UTC)}
    (item,) = feed_items([ev], {})
    assert item["user"] is None and item["count"] == 1
