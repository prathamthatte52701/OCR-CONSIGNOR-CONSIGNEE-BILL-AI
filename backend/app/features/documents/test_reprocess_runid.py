"""Feature 5: atomic Reprocess claim, processing run id, purge-both-parts, cleanup flag.
Fake documents only; the OCR pipeline is stubbed."""

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from bson import ObjectId
from fastapi.testclient import TestClient

from app.features.documents import router as r_mod
from app.features.documents.recovery import recover_interrupted_documents
from app.main import app
from testkit import current_db, make_document, make_user

JPEG = b"\xff\xd8\xff" + b"0" * 97
_REAL_JOB = r_mod._run_pipeline_and_update  # before any test stubs it


@pytest.fixture
def scheduled(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Stub the job: records what was scheduled, leaves the document 'processing'."""
    jobs: list[dict[str, Any]] = []

    async def stub(doc_id: ObjectId, *_: Any, **kw: Any) -> None:
        jobs.append({"id": doc_id, **kw})

    monkeypatch.setattr(r_mod, "_run_pipeline_and_update", stub)
    return jobs


def _reprocess(client: TestClient, user: dict[str, Any], doc: dict[str, Any]) -> Any:
    return client.post(f"/api/documents/{doc['id']}/reprocess", headers=user["headers"])


async def _row(doc_id: ObjectId) -> dict[str, Any]:
    row = await current_db().documents.find_one({"_id": doc_id})
    assert row is not None
    return row


# ---------------------------------------------------------------- R1 reprocess claim


async def test_double_reprocess_is_202_then_409_with_one_job(scheduled: list[Any]) -> None:
    user = await make_user()
    doc = await make_document(user["_id"])
    with TestClient(app, raise_server_exceptions=False) as client:
        first, second = _reprocess(client, user, doc), _reprocess(client, user, doc)
    assert (first.status_code, second.status_code) == (202, 409)
    assert second.json()["detail"] == "This document is already being processed. Please wait."
    assert len(scheduled) == 1
    row = await _row(doc["_id"])
    assert row["uploadStatus"] == "processing" and scheduled[0]["run_id"] == row["processingRunId"]


async def test_two_simultaneous_claims_have_one_winner() -> None:
    user = await make_user()
    doc = await make_document(user["_id"])
    filt = {"_id": doc["_id"], "uploadStatus": {"$in": ["processed", "failed"]}}

    async def claim(n: int) -> int:
        res = await current_db().documents.update_one(
            filt, {"$set": {"uploadStatus": "processing", "processingRunId": str(n)}}
        )
        return int(res.matched_count)

    results = await asyncio.gather(claim(1), claim(2))
    assert sorted(results) == [0, 1]


@pytest.mark.parametrize(
    ("status", "age", "code"),
    [
        ("processing", timedelta(minutes=1), 409),
        ("processing", timedelta(minutes=31), 202),
        ("failed", timedelta(0), 202),
    ],
)
async def test_reprocess_by_status_and_age(
    scheduled: list[Any], status: str, age: timedelta, code: int
) -> None:
    user = await make_user()
    doc = await make_document(
        user["_id"], uploadStatus=status, updatedAt=datetime.now(UTC) - age, processingError="old"
    )
    with TestClient(app, raise_server_exceptions=False) as client:
        assert _reprocess(client, user, doc).status_code == code
    assert len(scheduled) == (1 if code == 202 else 0)
    if code == 202:
        assert (await _row(doc["_id"]))["processingError"] is None


async def test_reprocess_with_purged_files_is_400(scheduled: list[Any]) -> None:
    user = await make_user()
    doc = await make_document(user["_id"], part1FilePurged=True)
    with TestClient(app, raise_server_exceptions=False) as client:
        assert _reprocess(client, user, doc).status_code == 400
    assert scheduled == []


async def test_reprocess_file_read_failure_changes_nothing(
    monkeypatch: pytest.MonkeyPatch, scheduled: list[Any]
) -> None:
    async def boom(_: Any) -> bytes:
        raise RuntimeError("gridfs down")

    monkeypatch.setattr(r_mod, "download_buffer", boom)
    user = await make_user()
    doc = await make_document(user["_id"], processingRunId="keep")
    with TestClient(app, raise_server_exceptions=False) as client:
        assert _reprocess(client, user, doc).status_code >= 400
    row = await _row(doc["_id"])
    assert row["uploadStatus"] == "processed" and row["processingRunId"] == "keep"
    assert scheduled == []


# ---------------------------------------------------------------- R2 run id


async def test_upload_and_bulk_store_a_run_id(scheduled: list[Any]) -> None:
    user = await make_user()
    with TestClient(app, raise_server_exceptions=False) as client:
        up = client.post(
            "/api/documents/upload",
            headers=user["headers"],
            files={"part1": ("a.jpg", JPEG, "image/jpeg"), "part2": ("b.jpg", JPEG, "image/jpeg")},
        )
        bulk = client.post(
            "/api/documents/bulk-upload",
            headers=user["headers"],
            files=[
                ("part1", ("a.jpg", JPEG, "image/jpeg")),
                ("part1", ("c.jpg", JPEG + b"1", "image/jpeg")),
                ("part2", ("b.jpg", JPEG, "image/jpeg")),
                ("part2", ("d.jpg", JPEG + b"2", "image/jpeg")),
            ],
        )
    assert up.status_code == 201 and bulk.status_code == 201
    ids = [up.json()["id"]] + [x["id"] for x in bulk.json()["results"]]
    runs = [(await _row(ObjectId(i)))["processingRunId"] for i in ids]
    assert len(set(runs)) == 3 and all(isinstance(r, str) and r for r in runs)


def _wrapper(monkeypatch: pytest.MonkeyPatch, outcome: str) -> None:
    async def pipeline(*_: Any) -> dict[str, Any]:
        if outcome == "fail":
            raise ValueError("ocr died")
        return {"invoiceNo": "NEW"}

    monkeypatch.setattr(r_mod, "run_full_pipeline", pipeline)
    monkeypatch.setattr(r_mod, "get_database", current_db)


async def _run(doc_id: ObjectId, run_id: str | None) -> None:
    await _REAL_JOB(
        doc_id, b"a", "image/jpeg", b"b", "image/jpeg", is_reprocess=False, run_id=run_id
    )


@pytest.mark.parametrize("outcome", ["ok", "fail"])
async def test_wrapper_writes_only_for_the_current_run(
    monkeypatch: pytest.MonkeyPatch, outcome: str
) -> None:
    _wrapper(monkeypatch, outcome)
    user = await make_user()
    doc = await make_document(user["_id"], uploadStatus="processing", processingRunId="new")
    await _run(doc["_id"], "old")
    row = await _row(doc["_id"])
    assert row["uploadStatus"] == "processing" and "invoiceNo" in row
    assert row["invoiceNo"] != "NEW"
    await _run(doc["_id"], "new")
    row = await _row(doc["_id"])
    assert row["uploadStatus"] == ("processed" if outcome == "ok" else "failed")


async def test_reprocess_ignores_the_old_jobs_late_result(
    monkeypatch: pytest.MonkeyPatch, scheduled: list[Any]
) -> None:
    user = await make_user()
    doc = await make_document(user["_id"], processingRunId="first")
    with TestClient(app, raise_server_exceptions=False) as client:
        assert _reprocess(client, user, doc).status_code == 202
    new_run = scheduled[0]["run_id"]
    assert new_run != "first"
    _wrapper(monkeypatch, "ok")
    await _run(doc["_id"], "first")  # the old job finishes late
    assert (await _row(doc["_id"]))["uploadStatus"] == "processing"
    await _run(doc["_id"], new_run)
    assert (await _row(doc["_id"]))["uploadStatus"] == "processed"


async def test_legacy_document_without_run_id_is_written_by_run_id_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _wrapper(monkeypatch, "ok")
    user = await make_user()
    doc = await make_document(user["_id"], uploadStatus="processing")
    assert "processingRunId" not in doc
    await _run(doc["_id"], None)
    assert (await _row(doc["_id"]))["uploadStatus"] == "processed"


async def test_recovery_passes_the_documents_run_id() -> None:
    user = await make_user()
    doc = await make_document(user["_id"], uploadStatus="processing", processingRunId="keepme")
    seen: list[Any] = []

    async def process(doc_id: ObjectId, *_: Any, **kw: Any) -> None:
        seen.append(kw["run_id"])

    async def read_file(_: Any) -> bytes:
        return JPEG

    await recover_interrupted_documents(db=current_db(), read_file=read_file, process=process)
    assert seen == ["keepme"] and (await _row(doc["_id"]))["processingRunId"] == "keepme"


async def test_bulk_crash_fallback_skips_a_document_whose_run_id_changed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = await make_user()
    doc = await make_document(user["_id"], uploadStatus="processing", processingRunId="newer")

    async def crash(*_: Any, **__: Any) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(r_mod, "_run_pipeline_and_update", crash)
    monkeypatch.setattr(r_mod, "get_database", current_db)
    await r_mod._run_sequentially([(doc["_id"], b"a", "image/jpeg", b"b", "image/jpeg", "older")])
    assert (await _row(doc["_id"]))["uploadStatus"] == "processing"


# ---------------------------------------------------------------- R3 purge both parts


def _purge(client: TestClient, user: dict[str, Any], doc: dict[str, Any]) -> Any:
    return client.post(f"/api/documents/{doc['id']}/purge-files", headers=user["headers"])


async def test_purge_marks_both_parts_and_blocks_downloads_and_reprocess() -> None:
    user = await make_user()
    doc = await make_document(user["_id"])
    with TestClient(app, raise_server_exceptions=False) as client:
        r = _purge(client, user, doc)
        assert r.status_code == 200 and r.json()["gridFsCleanupFailed"] is False
        assert r.json()["message"] == "Original files purged. Extracted data was preserved."
        row = await _row(doc["_id"])
        for p in ("part1", "part2"):
            assert row[f"{p}FilePurged"] is True and row[f"{p}GridFsFileId"] is None
        assert _purge(client, user, doc).status_code == 200  # safe to repeat
        for p in ("part1", "part2"):
            url = f"/api/documents/{doc['id']}/download/{p}"
            assert client.get(url, headers=user["headers"]).status_code == 400
        assert _reprocess(client, user, doc).status_code == 400


async def test_purge_part2_failure_still_purges_both_and_records_one_orphan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = await make_user()
    doc = await make_document(user["_id"])
    real = r_mod.delete_file
    calls: list[Any] = []

    async def flaky(file_id: ObjectId) -> None:
        calls.append(file_id)
        if file_id == doc["part2GridFsFileId"]:
            raise RuntimeError("gridfs down")
        await real(file_id)

    monkeypatch.setattr(r_mod, "delete_file", flaky)
    with TestClient(app, raise_server_exceptions=False) as client:
        r = _purge(client, user, doc)
        body = r.json()
        assert r.status_code == 200 and body["gridFsCleanupFailed"] is True
        assert "flagged for admin review" in body["message"]
        row = await _row(doc["_id"])
        assert row["part1FilePurged"] and row["part2FilePurged"]
        assert row["part1GridFsFileId"] is None and row["part2GridFsFileId"] is None
        orphans = await current_db().orphanedfiles.find({"documentId": doc["_id"]}).to_list(None)
        assert [o["fileId"] for o in orphans] == [doc["part2GridFsFileId"]]
        n = len(calls)
        assert _purge(client, user, doc).status_code == 200
        assert len(calls) == n  # nothing re-deleted


async def test_purge_skips_an_already_purged_part(monkeypatch: pytest.MonkeyPatch) -> None:
    user = await make_user()
    doc = await make_document(user["_id"], part1FilePurged=True)
    calls: list[Any] = []

    async def spy(file_id: ObjectId) -> None:
        calls.append(file_id)

    monkeypatch.setattr(r_mod, "delete_file", spy)
    with TestClient(app, raise_server_exceptions=False) as client:
        assert _purge(client, user, doc).status_code == 200
    assert calls == [doc["part2GridFsFileId"]]
    row = await _row(doc["_id"])
    assert row["part2FilePurged"] is True and row["part2GridFsFileId"] is None


# ---------------------------------------------------------------- R4 delete flag


@pytest.mark.parametrize("fail", [False, True])
async def test_delete_reports_cleanup_failure(monkeypatch: pytest.MonkeyPatch, fail: bool) -> None:
    async def broken(_: Any) -> None:
        raise RuntimeError("gridfs down")

    if fail:
        monkeypatch.setattr(r_mod, "delete_file", broken)
    user = await make_user()
    doc = await make_document(user["_id"])
    with TestClient(app, raise_server_exceptions=False) as client:
        r = client.delete(f"/api/documents/{doc['id']}", headers=user["headers"])
    assert r.status_code == 200 and r.json()["gridFsCleanupFailed"] is fail
    assert await current_db().documents.find_one({"_id": doc["_id"]}) is None
    orphans = await current_db().orphanedfiles.count_documents({"documentId": doc["_id"]})
    if fail:
        assert "flagged for admin review" in r.json()["message"] and orphans == 2
    else:
        assert r.json()["message"] == "Document permanently deleted." and orphans == 0
