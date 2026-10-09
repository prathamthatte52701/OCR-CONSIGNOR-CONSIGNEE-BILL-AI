"""T8: per-user isolation of every documents route (+ activity), the pending/rejected lockout on
every route, admin reach (via admin routes, audited), and soft-delete handling.

Matrix semantics (rows = routes, columns = actors):
  own       -> the owner of the document        other  -> a different approved user
  admin     -> an admin hitting the USER route   pending/rejected -> locked-out accounts
Set ISOLATION_MATRIX_OUT=<file.json> to dump the observed matrix (used for the test report)."""

import io
import json
import os
import zipfile
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.main import app
from testkit import PART1_BYTES, PART2_BYTES, current_db, make_document, make_user

PENDING = "Waiting for admin approval."
REJECTED = "Your request was not approved. Contact the admin."

# (name, method, path, json body, kind)  kind: "id" = addresses one document, "collection" = a list
ROUTES: list[tuple[str, str, str, dict[str, Any] | None, str]] = [
    ("GET /documents (list)", "GET", "/api/documents", None, "collection"),
    ("GET /documents/stats", "GET", "/api/documents/stats", None, "collection"),
    ("POST /documents/download-all", "POST", "/api/documents/download-all", None, "collection"),
    ("GET /auth/me/activity", "GET", "/api/auth/me/activity", None, "collection"),
    ("GET /documents/{id}", "GET", "/api/documents/{id}", None, "id"),
    ("GET /documents/{id}/download/part1", "GET", "/api/documents/{id}/download/part1", None, "id"),
    ("GET /documents/{id}/download/part2", "GET", "/api/documents/{id}/download/part2", None, "id"),
    (
        "PATCH /documents/{id}/correct",
        "PATCH",
        "/api/documents/{id}/correct",
        {"field": "reason", "value": "Tampered"},
        "id",
    ),
    ("POST /documents/{id}/reprocess", "POST", "/api/documents/{id}/reprocess", None, "id"),
    ("POST /documents/{id}/purge-files", "POST", "/api/documents/{id}/purge-files", None, "id"),
    ("DELETE /documents/{id}", "DELETE", "/api/documents/{id}", None, "id"),
]
OWN_OK = {"GET": 200, "POST": 200, "PATCH": 200, "DELETE": 200}

_matrix: dict[str, dict[str, int]] = {}


@pytest.fixture(scope="module")
def client() -> Iterator[TestClient]:
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    out = os.environ.get("ISOLATION_MATRIX_OUT")
    if out:
        with open(out, "w", encoding="utf-8") as fh:
            json.dump(_matrix, fh, indent=2)


@pytest.fixture(autouse=True)
def _no_real_pipeline(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reprocess schedules the OCR pipeline as a background task - never run real OCR here."""

    async def fake_pipeline(*_: Any, **__: Any) -> None:
        return None

    monkeypatch.setattr("app.features.documents.router._run_pipeline_and_update", fake_pipeline)


def _call(client: TestClient, method: str, path: str, headers: dict[str, str], body: Any) -> Any:
    return client.request(method, path, headers=headers, json=body)


async def _doc_snapshot(doc_id: Any) -> dict[str, Any] | None:
    return await current_db().documents.find_one({"_id": doc_id})


# --------------------------------------------------------------- cross-user: id routes


@pytest.mark.parametrize(
    ("name", "method", "path", "body", "kind"), [r for r in ROUTES if r[4] == "id"]
)
async def test_user_a_cannot_touch_user_bs_document_by_id(
    client: TestClient, name: str, method: str, path: str, body: Any, kind: str
) -> None:
    a, b = await make_user(), await make_user()
    doc = await make_document(b["_id"], reason="original")
    before = await _doc_snapshot(doc["_id"])

    r = _call(client, method, path.format(id=doc["id"]), a["headers"], body)
    assert r.status_code == 404, name  # never 403 (must not reveal that the id exists)
    assert doc["invoiceNo"] not in r.text and b"FAKE-PART" not in r.content

    after = await _doc_snapshot(doc["_id"])
    assert after == before, f"{name} changed someone else's document"
    # the owner still gets everything
    assert (
        client.get(f"/api/documents/{doc['id']}/download/part1", headers=b["headers"]).content
        == PART1_BYTES
    )
    assert (
        client.get(f"/api/documents/{doc['id']}/download/part2", headers=b["headers"]).content
        == PART2_BYTES
    )


@pytest.mark.parametrize(
    ("name", "method", "path", "body", "kind"), [r for r in ROUTES if r[4] == "id"]
)
async def test_owner_can_use_every_id_route(
    client: TestClient, name: str, method: str, path: str, body: Any, kind: str
) -> None:
    owner = await make_user()
    doc = await make_document(owner["_id"])
    r = _call(client, method, path.format(id=doc["id"]), owner["headers"], body)
    assert r.status_code in (200, 202), (name, r.status_code, r.text[:200])


async def test_nonexistent_and_foreign_ids_are_indistinguishable(client: TestClient) -> None:
    a, b = await make_user(), await make_user()
    doc = await make_document(b["_id"])
    foreign = client.get(f"/api/documents/{doc['id']}", headers=a["headers"])
    missing = client.get("/api/documents/000000000000000000000000", headers=a["headers"])
    assert foreign.status_code == missing.status_code == 404
    assert foreign.json() == missing.json() == {"detail": "Document not found."}


@pytest.mark.parametrize("bad_id", ["not-an-id", "123", "%20", "..%2f..%2fetc", "null", "{$ne:1}"])
async def test_malformed_ids_are_400_on_every_id_route(client: TestClient, bad_id: str) -> None:
    a = await make_user()
    for name, method, path, body, kind in ROUTES:
        if kind != "id":
            continue
        r = _call(client, method, path.format(id=bad_id), a["headers"], body)
        assert r.status_code in (400, 404, 405, 422), (name, bad_id, r.status_code)
        assert r.status_code != 500, (name, bad_id)


# ------------------------------------------------------------ cross-user: collections


async def test_list_shows_only_own_documents(client: TestClient) -> None:
    a, b = await make_user(), await make_user()
    mine = await make_document(a["_id"], invoiceNo="A-INV-1")
    theirs = await make_document(b["_id"], invoiceNo="B-INV-1")
    body = client.get("/api/documents", headers=a["headers"]).json()
    ids = {item["id"] for item in body["items"]}
    assert ids == {mine["id"]} and theirs["id"] not in ids and body["total"] == 1
    assert "userId" not in json.dumps(body)  # owner ids are never exposed to users


@pytest.mark.parametrize(
    "query",
    [
        "invoiceNo=B-INV-1",
        "invoiceNo=B-",
        "invoiceNo=.*",  # regex metacharacters are escaped, so this cannot match everything
        "consigneeCode=777",
        "date=2026",
        "range=year",
        "userId=OTHER",  # unknown param must be ignored, never trusted
        "invoiceNo[$ne]=zzz",
        "limit=100&page=1&userId=OTHER",
    ],
)
async def test_list_filters_and_injection_attempts_cannot_cross_users(
    client: TestClient, query: str
) -> None:
    a, b = await make_user(), await make_user()
    await make_document(a["_id"], invoiceNo="A-INV-1")
    theirs = await make_document(
        b["_id"], invoiceNo="B-INV-1", consigneeCode="777", challanDate="01/01/2026"
    )
    r = client.get("/api/documents?" + query.replace("OTHER", b["id"]), headers=a["headers"])
    assert r.status_code in (200, 422)
    if r.status_code == 200:
        assert theirs["id"] not in {item["id"] for item in r.json()["items"]}


async def test_stats_count_only_own_documents(client: TestClient) -> None:
    a, b = await make_user(), await make_user()
    await make_document(a["_id"])
    for _ in range(4):
        await make_document(b["_id"], uploadStatus="failed")
    stats = client.get("/api/documents/stats", headers=a["headers"]).json()
    assert stats["total"] == 1 and stats["failed"] == 0


async def test_download_all_zip_contains_only_own_documents(client: TestClient) -> None:
    a, b = await make_user(), await make_user()
    await make_document(a["_id"], invoiceNo="A-INV-1")
    await make_document(b["_id"], invoiceNo="B-INV-1")
    r = client.post("/api/documents/download-all", headers=a["headers"])
    assert r.status_code == 200 and r.headers["x-included-count"] == "1"
    names = zipfile.ZipFile(io.BytesIO(r.content)).namelist()
    assert names and all(n.startswith("A-INV-1/") for n in names)
    assert not any("B-INV-1" in n for n in names)


async def test_activity_shows_only_own_entries(client: TestClient) -> None:
    a, b = await make_user(), await make_user()
    doc = await make_document(b["_id"])
    client.patch(
        f"/api/documents/{doc['id']}/correct",
        json={"field": "reason", "value": "x"},
        headers=b["headers"],
    )
    client.delete(f"/api/documents/{doc['id']}", headers=b["headers"])
    items = client.get("/api/auth/me/activity", headers=a["headers"]).json()["items"]
    assert items == []  # B's corrections/deletes never show in A's activity
    assert client.get("/api/auth/me/activity", headers=b["headers"]).json()["total"] >= 2


# --------------------------------------------------------- pending / rejected / anonymous


async def test_pending_rejected_and_anonymous_are_locked_out_of_every_route(
    client: TestClient,
) -> None:
    owner = await make_user()
    doc = await make_document(owner["_id"])
    pending = await make_user(status="pending")
    rejected = await make_user(status="rejected")
    # rejected *through the admin API* too: bumps tokenVersion, so the old token is also stale
    admin = await make_user("admin")
    revoked = await make_user()
    assert (
        client.post(
            f"/api/admin/users/{revoked['id']}/reject", headers=admin["headers"]
        ).status_code
        == 200
    )

    for name, method, path, body, _kind in ROUTES:
        url = path.format(id=doc["id"])
        for label, headers, status, detail in (
            ("pending", pending["headers"], 403, PENDING),
            ("rejected", rejected["headers"], 403, REJECTED),
            ("rejected-old-token", revoked["headers"], 403, REJECTED),
            ("anonymous", {}, 401, None),
        ):
            r = _call(client, method, url, headers, body)
            assert r.status_code == status, (name, label, r.status_code)
            if detail:
                assert r.json()["detail"] == detail, (name, label)
            assert doc["invoiceNo"] not in r.text, (name, label)
    # the document is untouched by all of that
    assert await _doc_snapshot(doc["_id"]) is not None


async def test_locked_out_users_cannot_upload(client: TestClient) -> None:
    pending, rejected = await make_user(status="pending"), await make_user(status="rejected")
    tiny_jpeg = b"\xff\xd8\xff" + b"x" * 64
    for user in (pending, rejected):
        r = client.post(
            "/api/documents/upload",
            headers=user["headers"],
            files={
                "part1": ("a.jpg", tiny_jpeg, "image/jpeg"),
                "part2": ("b.jpg", tiny_jpeg, "image/jpeg"),
            },
        )
        assert r.status_code == 403
    assert await current_db().documents.count_documents({}) == 0


async def test_user_cannot_reach_admin_routes_for_documents(client: TestClient) -> None:
    a, b = await make_user(), await make_user()
    doc = await make_document(b["_id"])
    for path in (
        f"/api/admin/documents/{doc['id']}",
        f"/api/admin/documents/{doc['id']}/download/part1",
        "/api/admin/documents",
        "/api/admin/users",
        "/api/admin/logs",
    ):
        assert client.get(path, headers=a["headers"]).status_code == 403, path


# ------------------------------------------------------------------------ admin reach


async def test_admin_reaches_every_users_documents_through_admin_routes_with_audit(
    client: TestClient,
) -> None:
    admin, b = await make_user("admin"), await make_user()
    doc = await make_document(b["_id"])
    assert (
        client.get(f"/api/admin/documents/{doc['id']}", headers=admin["headers"]).status_code == 200
    )
    assert (
        client.get(
            f"/api/admin/documents/{doc['id']}/download/part2", headers=admin["headers"]
        ).content
        == PART2_BYTES
    )
    listing = client.get("/api/admin/documents", headers=admin["headers"]).json()
    assert doc["id"] in {item["id"] for item in listing["items"]}
    logs = await current_db().auditlogs.find({"userId": admin["_id"]}).to_list(None)
    assert {entry["action"] for entry in logs} >= {
        "admin_viewed_document",
        "admin_downloaded_part2",
    }


async def test_admin_is_still_owner_scoped_on_the_user_routes(client: TestClient) -> None:
    """Admin power lives only in /api/admin/* (audited). The user routes stay owner-only."""
    admin, b = await make_user("admin"), await make_user()
    doc = await make_document(b["_id"])
    assert client.get(f"/api/documents/{doc['id']}", headers=admin["headers"]).status_code == 404
    assert client.delete(f"/api/documents/{doc['id']}", headers=admin["headers"]).status_code == 404
    assert await _doc_snapshot(doc["_id"]) is not None


# ------------------------------------------------------------------- soft-deleted docs


async def test_legacy_soft_deleted_documents_are_treated_as_not_found(client: TestClient) -> None:
    """Soft-delete no longer exists (delete is permanent), but a leftover document flagged
    isDeleted=True must not resurface for its owner anywhere."""
    owner = await make_user()
    ghost = await make_document(owner["_id"], isDeleted=True, invoiceNo="GHOST-1")
    live = await make_document(owner["_id"], invoiceNo="LIVE-1")
    assert client.get(f"/api/documents/{ghost['id']}", headers=owner["headers"]).status_code == 404
    items = client.get("/api/documents", headers=owner["headers"]).json()["items"]
    assert {i["id"] for i in items} == {live["id"]}
    assert client.get("/api/documents/stats", headers=owner["headers"]).json()["total"] == 1
    zipped = client.post("/api/documents/download-all", headers=owner["headers"])
    assert not any("GHOST-1" in n for n in zipfile.ZipFile(io.BytesIO(zipped.content)).namelist())


# ------------------------------------------------------------------ the matrix (report)


async def test_isolation_matrix_is_exactly_as_designed(client: TestClient) -> None:
    owner, other, admin = await make_user(), await make_user(), await make_user("admin")
    pending, rejected = await make_user(status="pending"), await make_user(status="rejected")

    for name, method, path, body, kind in ROUTES:
        doc = await make_document(owner["_id"])
        url = path.format(id=doc["id"])
        observed = {
            "own": _call(client, method, url, owner["headers"], body).status_code,
            "other": _call(client, method, url, other["headers"], body).status_code,
            "admin(user route)": _call(client, method, url, admin["headers"], body).status_code,
            "pending": _call(client, method, url, pending["headers"], body).status_code,
            "rejected": _call(client, method, url, rejected["headers"], body).status_code,
        }
        _matrix[name] = observed
        assert observed["own"] in (200, 202), (name, observed)
        assert observed["pending"] == observed["rejected"] == 403, (name, observed)
        if kind == "id":
            # a second doc, since the own call above may have deleted/purged the first one
            assert observed["other"] == 404, (name, observed)
            assert observed["admin(user route)"] == 404, (name, observed)
        else:
            assert observed["other"] == 200 and observed["admin(user route)"] == 200, (
                name,
                observed,
            )
