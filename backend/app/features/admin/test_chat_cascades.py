"""Chat cascades: delete_user removes only that user's chat thread."""

from datetime import UTC, datetime
from typing import Any


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
