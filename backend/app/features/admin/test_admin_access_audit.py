"""T6: every admin route that opens ANOTHER user's document (detail, Part 1 / Part 2 files) writes
an audit entry: adminId (userId), targetUserId, documentId, action, time - before data is served."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.main import app
from testkit import PART1_BYTES, PART2_BYTES, current_db, make_document, make_user

ACTIONS = ("admin_viewed_document", "admin_downloaded_part1", "admin_downloaded_part2")


@pytest.fixture(scope="module")
def client() -> Iterator[TestClient]:
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


async def _access_logs() -> list[dict[str, Any]]:
    return await current_db().auditlogs.find({"action": {"$in": list(ACTIONS)}}).to_list(None)


async def test_admin_detail_view_is_audited_with_all_fields(client: TestClient) -> None:
    admin, owner = await make_user("admin"), await make_user()
    doc = await make_document(owner["_id"])
    r = client.get(f"/api/admin/documents/{doc['id']}", headers=admin["headers"])
    assert r.status_code == 200 and r.json()["id"] == doc["id"]
    logs = await _access_logs()
    assert len(logs) == 1
    log = logs[0]
    assert log["action"] == "admin_viewed_document"
    assert log["userId"] == admin["_id"]  # adminId
    assert log["context"] == {"targetUserId": owner["id"], "documentId": doc["id"]}
    assert abs(datetime.now(UTC) - log["createdAt"]) < timedelta(seconds=30)  # time


async def test_part1_and_part2_downloads_serve_bytes_and_are_audited(client: TestClient) -> None:
    admin, owner = await make_user("admin"), await make_user()
    doc = await make_document(owner["_id"])
    one = client.get(f"/api/admin/documents/{doc['id']}/download/part1", headers=admin["headers"])
    two = client.get(f"/api/admin/documents/{doc['id']}/download/part2", headers=admin["headers"])
    assert one.status_code == two.status_code == 200
    assert one.content == PART1_BYTES and two.content == PART2_BYTES
    assert one.headers["content-type"] == "image/jpeg"
    actions = sorted(entry["action"] for entry in await _access_logs())
    assert actions == ["admin_downloaded_part1", "admin_downloaded_part2"]
    for entry in await _access_logs():
        assert entry["userId"] == admin["_id"]
        assert entry["context"]["targetUserId"] == owner["id"]
        assert entry["context"]["documentId"] == doc["id"]


async def test_every_access_is_logged_not_deduplicated(client: TestClient) -> None:
    admin, owner = await make_user("admin"), await make_user()
    doc = await make_document(owner["_id"])
    for _ in range(3):
        client.get(f"/api/admin/documents/{doc['id']}", headers=admin["headers"])
    assert len(await _access_logs()) == 3


async def test_admin_opening_their_own_document_is_not_logged(client: TestClient) -> None:
    admin = await make_user("admin")
    doc = await make_document(admin["_id"])
    assert (
        client.get(f"/api/admin/documents/{doc['id']}", headers=admin["headers"]).status_code == 200
    )
    assert await _access_logs() == []


async def test_failed_lookups_write_no_entry(client: TestClient) -> None:
    admin = await make_user("admin")
    for path in (
        "/api/admin/documents/000000000000000000000000",
        "/api/admin/documents/not-an-id",
        "/api/admin/documents/000000000000000000000000/download/part1",
        "/api/admin/documents/not-an-id/download/part2",
    ):
        assert client.get(path, headers=admin["headers"]).status_code in (400, 404), path
    assert await _access_logs() == []


async def test_purged_or_missing_file_serves_nothing_and_logs_nothing(client: TestClient) -> None:
    admin, owner = await make_user("admin"), await make_user()
    purged = await make_document(owner["_id"], part1FilePurged=True)
    no_file = await make_document(owner["_id"], with_files=False)
    assert (
        client.get(
            f"/api/admin/documents/{purged['id']}/download/part1", headers=admin["headers"]
        ).status_code
        == 400
    )
    assert (
        client.get(
            f"/api/admin/documents/{no_file['id']}/download/part2", headers=admin["headers"]
        ).status_code
        == 404
    )
    assert await _access_logs() == []


async def test_non_admin_and_anonymous_get_nothing_and_leave_no_entry(client: TestClient) -> None:
    owner, other = await make_user(), await make_user()
    doc = await make_document(owner["_id"])
    for path in (
        f"/api/admin/documents/{doc['id']}",
        f"/api/admin/documents/{doc['id']}/download/part1",
        f"/api/admin/documents/{doc['id']}/download/part2",
    ):
        for headers, expected in ((other["headers"], 403), (owner["headers"], 403), ({}, 401)):
            r = client.get(path, headers=headers)
            assert r.status_code == expected, (path, expected)
            assert doc["invoiceNo"] not in r.text and b"FAKE-PART" not in r.content
    assert await _access_logs() == []


async def test_if_the_audit_write_fails_no_data_is_served(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    admin, owner = await make_user("admin"), await make_user()
    doc = await make_document(owner["_id"])

    async def broken(*_: Any, **__: Any) -> None:
        raise RuntimeError("audit store down")

    monkeypatch.setattr("app.features.admin.router.log_action", broken)
    for path in (
        f"/api/admin/documents/{doc['id']}",
        f"/api/admin/documents/{doc['id']}/download/part1",
    ):
        r = client.get(path, headers=admin["headers"])
        assert r.status_code == 500
        assert doc["invoiceNo"] not in r.text and PART1_BYTES not in r.content


async def test_entries_are_visible_in_the_admin_log_viewer_by_action(client: TestClient) -> None:
    admin, owner = await make_user("admin"), await make_user()
    doc = await make_document(owner["_id"])
    client.get(f"/api/admin/documents/{doc['id']}", headers=admin["headers"])
    client.get(f"/api/admin/documents/{doc['id']}/download/part1", headers=admin["headers"])
    viewed = client.get(
        "/api/admin/logs?action=admin_viewed_document", headers=admin["headers"]
    ).json()
    assert viewed["total"] == 1 and viewed["items"][0]["action"] == "admin_viewed_document"


async def test_owner_cannot_see_admin_access_entries_in_their_own_activity(
    client: TestClient,
) -> None:
    admin, owner = await make_user("admin"), await make_user()
    doc = await make_document(owner["_id"])
    client.get(f"/api/admin/documents/{doc['id']}", headers=admin["headers"])
    activity = client.get("/api/auth/me/activity", headers=owner["headers"]).json()
    assert all(item["action"] not in ACTIONS for item in activity["items"])
