"""Round 2: one shared purge for user + admin routes, stale jobs skipped before they start,
recovery _fail guarded by run id. Fake documents only; OCR stubbed."""

from datetime import UTC, datetime
from typing import Any

import pytest
from bson import ObjectId
from fastapi.testclient import TestClient

from app.features.documents import recovery
from app.features.documents import router as r_mod
from app.features.documents.file_purge import (
    DELETE_FAILED_MESSAGE,
    DELETE_OK_MESSAGE,
    PURGE_FAILED_MESSAGE,
    PURGE_OK_MESSAGE,
)
from app.main import app
from testkit import current_db, make_document, make_user

PURGE_DELETE = "app.features.documents.file_purge.delete_file"
_REAL_JOB = r_mod._run_pipeline_and_update  # before any test stubs it


async def _row(doc_id: ObjectId) -> dict[str, Any] | None:
    row: dict[str, Any] | None = await current_db().documents.find_one({"_id": doc_id})
    return row


def _routes(kind: str) -> tuple[str, str]:
    base = "/api/admin/documents" if kind == "admin" else "/api/documents"
    return base, kind


async def _actor(kind: str) -> tuple[dict[str, Any], dict[str, Any]]:
    owner = await make_user()
    actor = await make_user(role="admin") if kind == "admin" else owner
    doc = await make_document(owner["_id"])
    return actor, doc


# ---------------------------------------------------------------- shared purge, both routes


@pytest.mark.parametrize("kind", ["user", "admin"])
async def test_purge_both_files(kind: str) -> None:
    actor, doc = await _actor(kind)
    base, _ = _routes(kind)
    with TestClient(app, raise_server_exceptions=False) as client:
        r = client.post(f"{base}/{doc['id']}/purge-files", headers=actor["headers"])
    assert r.status_code == 200
    assert r.json() == {"message": PURGE_OK_MESSAGE, "gridFsCleanupFailed": False}
    row = await _row(doc["_id"])
    assert row is not None
    for p in ("part1", "part2"):
        assert row[f"{p}FilePurged"] is True and row[f"{p}GridFsFileId"] is None


@pytest.mark.parametrize("kind", ["user", "admin"])
async def test_purge_part2_failure_still_purges_both_and_is_repeatable(
    monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    actor, doc = await _actor(kind)
    base, _ = _routes(kind)
    calls: list[Any] = []

    async def flaky(file_id: ObjectId) -> None:
        calls.append(file_id)
        if file_id == doc["part2GridFsFileId"]:
            raise RuntimeError("gridfs down")

    monkeypatch.setattr(PURGE_DELETE, flaky)
    with TestClient(app, raise_server_exceptions=False) as client:
        r = client.post(f"{base}/{doc['id']}/purge-files", headers=actor["headers"])
        assert r.status_code == 200
        assert r.json() == {"message": PURGE_FAILED_MESSAGE, "gridFsCleanupFailed": True}
        row = await _row(doc["_id"])
        assert row is not None
        assert row["part1FilePurged"] and row["part2FilePurged"]
        assert row["part1GridFsFileId"] is None and row["part2GridFsFileId"] is None
        orphans = await current_db().orphanedfiles.find({"documentId": doc["_id"]}).to_list(None)
        assert [o["fileId"] for o in orphans] == [doc["part2GridFsFileId"]]
        n = len(calls)
        again = client.post(f"{base}/{doc['id']}/purge-files", headers=actor["headers"])
        assert again.status_code == 200 and len(calls) == n


@pytest.mark.parametrize("kind", ["user", "admin"])
async def test_purge_handles_only_the_unpurged_part(
    monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    owner = await make_user()
    actor = await make_user(role="admin") if kind == "admin" else owner
    doc = await make_document(owner["_id"], part1FilePurged=True)
    calls: list[Any] = []

    async def spy(file_id: ObjectId) -> None:
        calls.append(file_id)

    monkeypatch.setattr(PURGE_DELETE, spy)
    base, _ = _routes(kind)
    with TestClient(app, raise_server_exceptions=False) as client:
        r = client.post(f"{base}/{doc['id']}/purge-files", headers=actor["headers"])
    assert r.status_code == 200 and calls == [doc["part2GridFsFileId"]]


# ---------------------------------------------------------------- admin delete


@pytest.mark.parametrize("fail", [False, True])
async def test_admin_delete_reports_cleanup_failure(
    monkeypatch: pytest.MonkeyPatch, fail: bool
) -> None:
    async def broken(_: Any) -> None:
        raise RuntimeError("gridfs down")

    if fail:
        monkeypatch.setattr(PURGE_DELETE, broken)
    admin = await make_user(role="admin")
    owner = await make_user()
    doc = await make_document(owner["_id"])
    with TestClient(app, raise_server_exceptions=False) as client:
        r = client.delete(f"/api/admin/documents/{doc['id']}", headers=admin["headers"])
    assert r.status_code == 200 and r.json()["gridFsCleanupFailed"] is fail
    assert r.json()["message"] == (DELETE_FAILED_MESSAGE if fail else DELETE_OK_MESSAGE)
    assert await _row(doc["_id"]) is None
    orphans = await current_db().orphanedfiles.count_documents({"documentId": doc["_id"]})
    assert orphans == (2 if fail else 0)


# ---------------------------------------------------------------- stale start


@pytest.fixture
def pipeline(monkeypatch: pytest.MonkeyPatch) -> list[bool]:
    calls: list[bool] = []

    async def fake(*_: Any) -> dict[str, Any]:
        calls.append(True)
        return {"invoiceNo": "NEW"}

    monkeypatch.setattr(r_mod, "run_full_pipeline", fake)
    monkeypatch.setattr(r_mod, "get_database", current_db)
    return calls


async def _job(doc_id: ObjectId, run_id: str | None) -> None:
    await _REAL_JOB(
        doc_id, b"a", "image/jpeg", b"b", "image/jpeg", is_reprocess=False, run_id=run_id
    )


async def test_deleted_document_job_never_starts_the_pipeline(pipeline: list[bool]) -> None:
    await _job(ObjectId(), "r1")
    assert pipeline == []


async def test_reprocessed_document_old_job_skips_and_new_job_runs(pipeline: list[bool]) -> None:
    user = await make_user()
    doc = await make_document(user["_id"], uploadStatus="processing", processingRunId="new")
    await _job(doc["_id"], "old")
    assert pipeline == []
    await _job(doc["_id"], "new")
    assert pipeline == [True]


async def test_legacy_document_runs_with_run_id_none(pipeline: list[bool]) -> None:
    user = await make_user()
    doc = await make_document(user["_id"], uploadStatus="processing")
    await _job(doc["_id"], None)
    assert pipeline == [True]


async def test_bulk_set_deleted_before_its_turn_is_skipped_and_the_rest_run(
    pipeline: list[bool],
) -> None:
    user = await make_user()
    docs = [
        await make_document(user["_id"], uploadStatus="processing", processingRunId=f"r{i}")
        for i in range(3)
    ]
    await current_db().documents.delete_one({"_id": docs[1]["_id"]})
    jobs = [(d["_id"], b"a", "image/jpeg", b"b", "image/jpeg", f"r{i}") for i, d in enumerate(docs)]
    await r_mod._run_sequentially(jobs)
    assert len(pipeline) == 2
    for i in (0, 2):
        row = await _row(docs[i]["_id"])
        assert row is not None and row["uploadStatus"] == "processed"


# ---------------------------------------------------------------- recovery _fail


@pytest.mark.parametrize(
    ("doc_run", "stored_run", "expect_failed"),
    [("a", "a", True), ("a", "b", False), (None, None, True)],
)
async def test_recovery_fail_only_for_the_same_run(
    doc_run: str | None, stored_run: str | None, expect_failed: bool
) -> None:
    user = await make_user()
    fields: dict[str, Any] = {"uploadStatus": "processing", "updatedAt": datetime.now(UTC)}
    if stored_run is not None:
        fields["processingRunId"] = stored_run
    doc = await make_document(user["_id"], **fields)
    snapshot = dict(doc)
    if doc_run is None:
        snapshot.pop("processingRunId", None)
    else:
        snapshot["processingRunId"] = doc_run
    await recovery._fail(current_db(), snapshot, "err", "test")
    row = await _row(doc["_id"])
    assert row is not None
    assert (row["uploadStatus"] == "failed") is expect_failed
