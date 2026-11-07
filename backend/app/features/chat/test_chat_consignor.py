"""Consignor-specific chat checks: approval gate on every chat route, and chat never shows up in
My Activity (chat actions are not in DOCUMENT_ACTIONS / ACCOUNT_ACTIONS)."""

from typing import Any

import pytest

from app.features.chat.test_chat_permissions import ROUTES, _call  # noqa: F401


@pytest.mark.parametrize("status", ["pending", "rejected", "revoked"])
@pytest.mark.parametrize("method,path,body", ROUTES)
async def test_not_approved_user_gets_403_on_every_chat_route(
    client: Any, make_user: Any, status: str, method: str, path: str, body: Any
) -> None:
    u = await make_user(status=status)
    r = await _call(client, u, method, path, body)
    assert r.status_code == 403
    assert r.json()["detail"]["code"] != "PASSWORD_CHANGE_REQUIRED"


@pytest.mark.parametrize("method,path,body", ROUTES)
async def test_must_change_password_403_on_every_chat_route(
    client: Any, make_user: Any, db: Any, method: str, path: str, body: Any
) -> None:
    u = await make_user()
    await db.users.update_one({"_id": u.id}, {"$set": {"mustChangePassword": True}})
    r = await _call(client, u, method, path, body)
    assert r.status_code == 403 and r.json()["detail"]["code"] == "PASSWORD_CHANGE_REQUIRED"


async def test_chat_actions_never_appear_in_my_activity(
    client: Any, make_user: Any, db: Any
) -> None:
    from app.core.audit_log import log_action

    adm, u = await make_user(role="admin"), await make_user()
    sent = await client.post(
        "/api/chat/messages", headers=u.headers, json={"toAdminId": str(adm.id), "text": "hi"}
    )
    assert sent.status_code in (200, 201), sent.text
    await log_action(u.id, "chat_clear", {"userId": str(u.id)})
    await log_action(u.id, "chat_clear_blocked", {"reason": "wrong_password"})
    await log_action(u.id, "login", {})  # control: a real account action does show up

    r = await client.get("/api/auth/me/activity", headers=u.headers)
    assert r.status_code == 200, r.text
    actions = [e["action"] for e in r.json()["items"]]
    assert actions == ["login"]
