"""Chat cascades: delete_user removes only that user's chat thread."""

from datetime import UTC, datetime
from typing import Any

from app.core.config import settings
from app.features.chat.test_chat_files import img_bytes, up


def _msg(thread: Any, from_id: Any, role: str) -> dict[str, Any]:
    now = datetime.now(UTC)
    return {
        "threadUserId": thread,
        "fromId": from_id,
        "fromRole": role,
        "text": "hi",
        "createdAt": now,
        "updatedAt": now,
    }


async def _delete(client: Any, admin: Any, user: Any) -> None:
    r = await client.delete(f"/api/admin/users/{user.id}", headers=admin.headers)
    assert r.status_code == 200, r.text


async def test_delete_user_removes_only_their_thread(client: Any, db: Any, make_user: Any) -> None:
    admin, a, b = await make_user(role="admin"), await make_user(), await make_user()
    await db.chatmessages.insert_many(
        [
            _msg(a.id, a.id, "user"),
            _msg(a.id, admin.id, "admin"),
            _msg(b.id, b.id, "user"),
            _msg(b.id, admin.id, "admin"),  # admin-authored, in B's thread: must stay
        ]
    )
    await _delete(client, admin, a)
    assert await db.chatmessages.count_documents({"threadUserId": a.id}) == 0
    assert await db.chatmessages.count_documents({"threadUserId": b.id}) == 2
    assert await db.chatmessages.count_documents({"fromId": admin.id}) == 1


async def test_delete_user_without_messages(client: Any, db: Any, make_user: Any) -> None:
    admin, a, b = await make_user(role="admin"), await make_user(), await make_user()
    await db.chatmessages.insert_one(_msg(b.id, b.id, "user"))
    await _delete(client, admin, a)
    assert await db.users.find_one({"_id": a.id}) is None
    assert await db.chatmessages.count_documents({}) == 1


async def test_delete_user_removes_their_chat_files_and_leaves_others(
    client: Any, db: Any, make_user: Any
) -> None:
    admin, a, b = await make_user(role="admin"), await make_user(), await make_user()
    for u in (a, b):
        r = await up(client, u, img_bytes(), "pic.jpg", to=admin)
        assert r.status_code == 201, r.text
    assert await db["chatfs.files"].count_documents({}) == 2

    await _delete(client, admin, a)

    assert await db.chatmessages.count_documents({"threadUserId": a.id}) == 0
    assert await db.chatattachments.count_documents({"threadUserId": a.id}) == 0
    assert await db["chatfs.files"].count_documents({}) == 1  # only B's file is left
    assert await db.chatattachments.count_documents({"threadUserId": b.id}) == 1
    assert await db.chatmessages.count_documents({"threadUserId": b.id}) == 1
    log = await db.auditlogs.find_one({"action": "user_deleted"})
    assert log["context"]["chatFilesDeleted"] == 1 and log["context"]["chatBytesFreed"] > 0


async def test_system_reports_chat_storage_without_hosts(
    client: Any, db: Any, make_user: Any
) -> None:
    admin, u = await make_user(role="admin"), await make_user()
    empty = (await client.get("/api/admin/system", headers=admin.headers)).json()
    assert empty["chat"] == {"files": 0, "bytes": 0}

    data = img_bytes()
    assert (await up(client, u, data, "pic.jpg", to=admin)).status_code == 201
    res = await client.get("/api/admin/system", headers=admin.headers)
    body = res.json()
    assert body["chat"]["files"] == 1 and body["chat"]["bytes"] > 0
    assert settings.mongo_uri not in res.text and "mongodb" not in res.text.lower()
    assert "pic.jpg" not in res.text


async def test_maintenance_activity_shows_chat_clear_without_text_or_names(
    client: Any, db: Any, make_user: Any
) -> None:
    admin, u = await make_user(role="admin"), await make_user()
    sent = await client.post(
        "/api/chat/messages",
        headers=u.headers,
        json={"toAdminId": str(admin.id), "text": "TOPSECRET-TEXT"},
    )
    assert sent.status_code in (200, 201), sent.text
    r = await client.post(
        "/api/chat/clear",
        headers=admin.headers,
        json={"userId": str(u.id), "olderThan": "all", "confirm": "DELETE"},
    )
    assert r.status_code == 200, r.text
    await client.post(
        "/api/chat/clear-all",
        headers=admin.headers,
        json={"password": "Wr0ng!Passw0rd-x", "confirm": "DELETE"},
    )

    res = await client.get("/api/admin/maintenance-activity", headers=admin.headers)
    assert res.status_code == 200
    items = {i["action"]: i for i in res.json()["items"]}
    cleared = items["chat_cleared"]
    assert cleared["context"]["deleted"] == 1 and cleared["context"]["scope"] == "user"
    assert items["chat_clear_blocked"]["context"] == {"reason": "wrong_password"}
    assert "TOPSECRET" not in res.text and u.username not in res.text and str(u.id) not in res.text
