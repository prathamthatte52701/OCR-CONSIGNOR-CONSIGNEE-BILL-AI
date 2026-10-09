"""T7: a user can never change their own email (403); an admin can (validated, unique, sessions
revoked via tokenVersion bump, audited). Other profile fields still work for the user."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.main import app
from testkit import PASSWORD, current_db, make_user


@pytest.fixture(scope="module")
def client() -> Iterator[TestClient]:
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


# ----------------------------------------------------------------- PATCH /api/auth/me


async def test_user_cannot_change_own_email(client: TestClient) -> None:
    user = await make_user()
    r = client.patch("/api/auth/me", json={"email": "new@example.invalid"}, headers=user["headers"])
    assert r.status_code == 403
    assert "admin" in r.json()["detail"].lower()
    stored = await current_db().users.find_one({"_id": user["_id"]})
    assert stored is not None and stored["email"] == user["email"]


async def test_rejected_email_change_applies_nothing_else(client: TestClient) -> None:
    user = await make_user(username="keepme")
    r = client.patch(
        "/api/auth/me",
        json={"username": "hacked", "email": "new@example.invalid"},
        headers=user["headers"],
    )
    assert r.status_code == 403
    stored = await current_db().users.find_one({"_id": user["_id"]})
    assert stored is not None and stored["username"] == "keepme"  # no partial update


async def test_other_fields_still_editable(client: TestClient) -> None:
    user = await make_user()
    r = client.patch("/api/auth/me", json={"username": "newname"}, headers=user["headers"])
    assert r.status_code == 200 and r.json()["username"] == "newname"
    assert r.json()["email"] == user["email"]


@pytest.mark.parametrize("variant", ["same", "upper", "padded"])
async def test_resending_the_unchanged_email_is_allowed(client: TestClient, variant: str) -> None:
    user = await make_user()
    email = {"same": user["email"], "upper": user["email"].upper(), "padded": f"  {user['email']} "}
    r = client.patch(
        "/api/auth/me",
        json={"username": "viaform", "email": email[variant]},
        headers=user["headers"],
    )
    assert r.status_code == 200 and r.json()["username"] == "viaform"


@pytest.mark.parametrize(
    "bad_email",
    ["", "garbage", "other@example.invalid", "a@b", "<script>@x.io", "x" * 200 + "@y.io"],
)
async def test_any_different_email_value_is_403(client: TestClient, bad_email: str) -> None:
    user = await make_user()
    r = client.patch("/api/auth/me", json={"email": bad_email}, headers=user["headers"])
    assert r.status_code == 403


async def test_null_email_is_ignored(client: TestClient) -> None:
    user = await make_user()
    r = client.patch(
        "/api/auth/me", json={"username": "nullmail", "email": None}, headers=user["headers"]
    )
    assert r.status_code == 200 and r.json()["email"] == user["email"]


async def test_cannot_take_over_another_users_email(client: TestClient) -> None:
    victim, attacker = await make_user(), await make_user()
    r = client.patch("/api/auth/me", json={"email": victim["email"]}, headers=attacker["headers"])
    assert r.status_code == 403
    assert await current_db().users.count_documents({"email": victim["email"]}) == 1


async def test_anonymous_cannot_patch_profile(client: TestClient) -> None:
    assert client.patch("/api/auth/me", json={"username": "abc"}).status_code == 401


# ----------------------------------------------------------- PATCH /api/admin/users/{id}


async def test_admin_can_change_a_users_email_and_it_is_audited(client: TestClient) -> None:
    admin, user = await make_user("admin"), await make_user()
    r = client.patch(
        f"/api/admin/users/{user['id']}",
        json={"email": "  New.Name@Example.INVALID "},
        headers=admin["headers"],
    )
    assert r.status_code == 200 and r.json()["email"] == "new.name@example.invalid"  # normalized
    log = await current_db().auditlogs.find_one({"action": "user_updated"})
    assert log is not None and log["userId"] == admin["_id"]
    assert log["context"]["previousEmail"] == user["email"]
    assert log["context"]["newEmail"] == "new.name@example.invalid"
    assert "email" in log["context"]["fields"]


async def test_email_change_revokes_sessions_and_user_logs_in_with_the_new_address(
    client: TestClient,
) -> None:
    admin, user = await make_user("admin"), await make_user()
    assert client.get("/api/auth/me", headers=user["headers"]).status_code == 200
    client.patch(
        f"/api/admin/users/{user['id']}",
        json={"email": "moved@example.invalid"},
        headers=admin["headers"],
    )
    stored = await current_db().users.find_one({"_id": user["_id"]})
    assert stored is not None and stored["tokenVersion"] == 1
    assert client.get("/api/auth/me", headers=user["headers"]).status_code == 401  # old token dead
    old = client.post("/api/auth/login", json={"email": user["email"], "password": PASSWORD})
    new = client.post(
        "/api/auth/login", json={"email": "moved@example.invalid", "password": PASSWORD}
    )
    assert old.status_code == 401 and new.status_code == 200


async def test_admin_cannot_use_an_email_that_belongs_to_someone_else(client: TestClient) -> None:
    admin, one, two = await make_user("admin"), await make_user(), await make_user()
    for attempt in (two["email"], two["email"].upper(), f" {two['email']} "):
        r = client.patch(
            f"/api/admin/users/{one['id']}", json={"email": attempt}, headers=admin["headers"]
        )
        assert r.status_code == 400 and "already in use" in r.json()["detail"]
    stored = await current_db().users.find_one({"_id": one["_id"]})
    assert stored is not None and stored["email"] == one["email"] and stored["tokenVersion"] == 0


@pytest.mark.parametrize("bad", ["", "no-at-sign", "a@b", "two@@x.io", "sp ace@x.io"])
async def test_admin_email_must_be_valid(client: TestClient, bad: str) -> None:
    admin, user = await make_user("admin"), await make_user()
    r = client.patch(
        f"/api/admin/users/{user['id']}", json={"email": bad}, headers=admin["headers"]
    )
    assert r.status_code == 400
    stored = await current_db().users.find_one({"_id": user["_id"]})
    assert stored is not None and stored["email"] == user["email"]


async def test_admin_setting_the_same_email_is_a_noop(client: TestClient) -> None:
    admin, user = await make_user("admin"), await make_user()
    r = client.patch(
        f"/api/admin/users/{user['id']}",
        json={"email": user["email"].upper()},
        headers=admin["headers"],
    )
    assert r.status_code == 200
    stored = await current_db().users.find_one({"_id": user["_id"]})
    assert stored is not None and stored["tokenVersion"] == 0  # no needless logout
    assert await current_db().auditlogs.count_documents({"action": "user_updated"}) == 0


async def test_non_admin_cannot_use_the_admin_email_route(client: TestClient) -> None:
    attacker, victim = await make_user(), await make_user()
    for target in (victim, attacker):
        r = client.patch(
            f"/api/admin/users/{target['id']}",
            json={"email": "evil@example.invalid"},
            headers=attacker["headers"],
        )
        assert r.status_code == 403
    assert (
        client.patch(f"/api/admin/users/{victim['id']}", json={"email": "e@x.io"}).status_code
        == 401
    )


async def test_admin_username_and_role_edits_do_not_log_anyone_out(client: TestClient) -> None:
    admin, user = await make_user("admin"), await make_user()
    r = client.patch(
        f"/api/admin/users/{user['id']}", json={"username": "renamed"}, headers=admin["headers"]
    )
    assert r.status_code == 200
    assert client.get("/api/auth/me", headers=user["headers"]).status_code == 200  # still valid


async def test_admin_edit_of_unknown_or_malformed_user(client: TestClient) -> None:
    admin = await make_user("admin")
    body = {"email": "x@example.invalid"}
    assert (
        client.patch(
            "/api/admin/users/000000000000000000000000", json=body, headers=admin["headers"]
        ).status_code
        == 404
    )
    assert (
        client.patch("/api/admin/users/not-an-id", json=body, headers=admin["headers"]).status_code
        == 400
    )
