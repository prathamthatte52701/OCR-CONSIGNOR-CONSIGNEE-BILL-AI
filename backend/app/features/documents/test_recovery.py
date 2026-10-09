"""T12: restart recovery of documents stuck in "processing".

Everything uses fake stuck documents with tiny synthetic GridFS files and a MOCKED OCR step
(a recorder passed in through the `process` seam) - no real document, no real OCR."""

import asyncio
import time
from collections.abc import Iterator
from typing import Any

import pytest
from bson import ObjectId
from fastapi.testclient import TestClient
from motor.motor_asyncio import AsyncIOMotorGridFSBucket

from app.core.config import settings
from app.features.documents import recovery
from app.features.documents.recovery import (
    ATTEMPTS_EXHAUSTED_ERROR,
    FILES_MISSING_ERROR,
    MAX_RECOVERY_ATTEMPTS,
    recover_interrupted_documents,
)
from app.main import app
from testkit import PART1_BYTES, PART2_BYTES, current_db, make_document, make_user


class Recorder:
    """Stand-in for the OCR pipeline: records every call, optionally misbehaves."""

    def __init__(self, behaviour: str = "ok") -> None:
        self.calls: list[dict[str, Any]] = []
        self.in_flight = 0
        self.max_in_flight = 0
        self.behaviour = behaviour
        self.attempts_seen_in_db: list[int] = []

    async def __call__(
        self,
        doc_id: ObjectId,
        part1: bytes,
        part1_mime: str,
        part2: bytes,
        part2_mime: str,
        *,
        is_reprocess: bool,
    ) -> None:
        self.in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self.in_flight)
        try:
            await asyncio.sleep(0.01)  # give a concurrent run the chance to overlap
            stored = await current_db().documents.find_one({"_id": doc_id})
            self.attempts_seen_in_db.append(int(stored.get("recoveryAttempts", 0)))
            self.calls.append(
                {
                    "id": doc_id,
                    "p1": part1,
                    "p2": part2,
                    "m1": part1_mime,
                    "m2": part2_mime,
                    "re": is_reprocess,
                }
            )
            if self.behaviour == "raise":
                raise RuntimeError("OCR exploded")
            if self.behaviour == "ok":
                await current_db().documents.update_one(
                    {"_id": doc_id}, {"$set": {"uploadStatus": "processed"}}
                )
            # behaviour == "die": leaves the document "processing", like a hard crash would
        finally:
            self.in_flight -= 1


async def _read_file(file_id: ObjectId) -> bytes:
    stream = await AsyncIOMotorGridFSBucket(current_db()).open_download_stream(file_id)
    return await stream.read()


async def _run(process: Recorder) -> dict[str, int]:
    return await recover_interrupted_documents(
        db=current_db(), read_file=_read_file, process=process
    )


async def _stuck(owner_id: ObjectId, **fields: Any) -> dict[str, Any]:
    return await make_document(owner_id, uploadStatus="processing", **fields)


async def _doc(doc_id: ObjectId) -> dict[str, Any]:
    stored = await current_db().documents.find_one({"_id": doc_id})
    assert stored is not None
    return stored


# ------------------------------------------------------------------ the core behaviour


async def test_a_stuck_document_is_processed_from_its_stored_files() -> None:
    owner = await make_user()
    doc = await _stuck(owner["_id"])
    rec = Recorder()
    summary = await _run(rec)
    assert summary == {"found": 1, "requeued": 1, "failed_attempts": 0, "failed_missing_files": 0}
    assert len(rec.calls) == 1
    call = rec.calls[0]
    assert call["id"] == doc["_id"] and call["p1"] == PART1_BYTES and call["p2"] == PART2_BYTES
    assert call["m1"] == call["m2"] == "image/jpeg" and call["re"] is False
    assert (await _doc(doc["_id"]))["uploadStatus"] == "processed"


async def test_the_attempt_is_counted_BEFORE_processing_so_a_crash_still_counts() -> None:
    owner = await make_user()
    doc = await _stuck(owner["_id"])
    rec = Recorder()
    await _run(rec)
    assert rec.attempts_seen_in_db == [1]  # already 1 in the database while OCR was running
    assert (await _doc(doc["_id"]))["recoveryAttempts"] == 1


async def test_a_document_with_one_earlier_attempt_gets_its_second_chance() -> None:
    owner = await make_user()
    doc = await _stuck(owner["_id"], recoveryAttempts=1)
    rec = Recorder()
    summary = await _run(rec)
    assert summary["requeued"] == 1 and len(rec.calls) == 1
    assert (await _doc(doc["_id"]))["recoveryAttempts"] == 2


async def test_after_two_attempts_the_document_is_failed_not_retried() -> None:
    owner = await make_user()
    doc = await _stuck(owner["_id"], recoveryAttempts=MAX_RECOVERY_ATTEMPTS)
    rec = Recorder()
    summary = await _run(rec)
    assert rec.calls == []  # OCR is NOT run again
    assert summary["failed_attempts"] == 1
    stored = await _doc(doc["_id"])
    assert stored["uploadStatus"] == "failed"
    assert stored["processingError"] == ATTEMPTS_EXHAUSTED_ERROR
    assert "restart" in stored["processingError"] and "Reprocess" in stored["processingError"]
    audit = await current_db().auditlogs.find_one({"action": "document_recovery_failed"})
    assert audit is not None and audit["context"]["documentId"] == str(doc["_id"])
    assert audit["userId"] == owner["_id"]


async def test_a_document_that_keeps_killing_the_process_cannot_loop_forever() -> None:
    """Simulates a hard crash on every boot (the OCR step never finishes): boot 1 and 2 retry,
    boot 3 gives up - the loop is bounded."""
    owner = await make_user()
    doc = await _stuck(owner["_id"])
    results = []
    for _boot in range(5):
        rec = Recorder("die")
        await _run(rec)
        results.append((len(rec.calls), (await _doc(doc["_id"]))["uploadStatus"]))
    assert results == [
        (1, "processing"),
        (1, "processing"),
        (0, "failed"),
        (0, "failed"),  # no longer "processing", so later boots ignore it entirely
        (0, "failed"),
    ]


# ------------------------------------------------------------------ missing files


@pytest.mark.parametrize(
    "overrides",
    [
        {"part1FilePurged": True},
        {"part2FilePurged": True},
        {"part1GridFsFileId": None},
        {"part2GridFsFileId": None},
    ],
)
async def test_missing_or_purged_files_mark_the_document_failed_and_record_it(
    overrides: dict[str, Any],
) -> None:
    owner = await make_user()
    doc = await _stuck(owner["_id"], **overrides)
    rec = Recorder()
    summary = await _run(rec)
    assert rec.calls == [] and summary["failed_missing_files"] == 1
    stored = await _doc(doc["_id"])
    assert stored["uploadStatus"] == "failed" and stored["processingError"] == FILES_MISSING_ERROR
    audit = await current_db().auditlogs.find_one({"action": "document_recovery_failed"})
    assert audit is not None and audit["context"]["reason"] == "stored files missing"


async def test_ids_that_point_at_nothing_in_gridfs_are_failed_not_crashed() -> None:
    owner = await make_user()
    doc = await _stuck(
        owner["_id"], with_files=False, part1GridFsFileId=ObjectId(), part2GridFsFileId=ObjectId()
    )
    rec = Recorder()
    summary = await _run(rec)
    assert rec.calls == [] and summary["failed_missing_files"] == 1
    assert (await _doc(doc["_id"]))["uploadStatus"] == "failed"


async def test_a_document_with_no_stored_files_at_all_is_failed() -> None:
    owner = await make_user()
    doc = await _stuck(owner["_id"], with_files=False)
    rec = Recorder()
    await _run(rec)
    assert rec.calls == [] and (await _doc(doc["_id"]))["processingError"] == FILES_MISSING_ERROR


# ------------------------------------------------------------------ selection / ordering


async def test_only_processing_documents_are_touched() -> None:
    owner = await make_user()
    others = [
        await make_document(owner["_id"], uploadStatus=status)
        for status in ("processed", "failed", "uploaded")
    ]
    stuck = await _stuck(owner["_id"])
    rec = Recorder()
    summary = await _run(rec)
    assert summary["found"] == 1 and [c["id"] for c in rec.calls] == [stuck["_id"]]
    for other in others:
        stored = await _doc(other["_id"])
        assert stored["uploadStatus"] == other["uploadStatus"] and "recoveryAttempts" not in stored


async def test_documents_are_processed_one_at_a_time_oldest_first() -> None:
    owner = await make_user()
    from datetime import UTC, datetime, timedelta

    now = datetime.now(UTC)
    newest = await _stuck(owner["_id"], createdAt=now)
    oldest = await _stuck(owner["_id"], createdAt=now - timedelta(hours=2))
    middle = await _stuck(owner["_id"], createdAt=now - timedelta(hours=1))
    rec = Recorder()
    await _run(rec)
    assert [c["id"] for c in rec.calls] == [oldest["_id"], middle["_id"], newest["_id"]]
    assert rec.max_in_flight == 1  # never two OCR runs at once


async def test_one_failing_document_does_not_stop_the_others() -> None:
    owner = await make_user()
    from datetime import UTC, datetime, timedelta

    now = datetime.now(UTC)
    bad = await _stuck(owner["_id"], createdAt=now - timedelta(hours=1))
    good = await _stuck(owner["_id"], createdAt=now)
    rec = Recorder("raise")
    summary = await _run(rec)
    assert len(rec.calls) == 2  # the second document was still attempted
    assert summary["failed_attempts"] == 2
    for doc in (bad, good):
        stored = await _doc(doc["_id"])
        assert stored["uploadStatus"] == "failed" and "OCR exploded" in stored["processingError"]


async def test_a_previously_processed_document_is_requeued_as_a_reprocess() -> None:
    from datetime import UTC, datetime

    owner = await make_user()
    await _stuck(owner["_id"], processedAt=datetime.now(UTC))
    rec = Recorder()
    await _run(rec)
    assert rec.calls[0]["re"] is True


async def test_running_recovery_twice_does_not_process_a_finished_document_again() -> None:
    owner = await make_user()
    await _stuck(owner["_id"])
    first, second = Recorder(), Recorder()
    await _run(first)
    await _run(second)
    assert len(first.calls) == 1 and second.calls == []


async def test_nothing_stuck_is_a_cheap_no_op() -> None:
    owner = await make_user()
    await make_document(owner["_id"])
    rec = Recorder()
    assert await _run(rec) == {
        "found": 0,
        "requeued": 0,
        "failed_attempts": 0,
        "failed_missing_files": 0,
    }
    assert rec.calls == []


async def test_a_document_deleted_while_recovering_is_skipped() -> None:
    owner = await make_user()
    doc = await _stuck(owner["_id"])
    rec = Recorder()

    async def read_then_delete(file_id: ObjectId) -> bytes:
        data = await _read_file(file_id)
        await current_db().documents.delete_one({"_id": doc["_id"]})  # user deleted it meanwhile
        return data

    summary = await recover_interrupted_documents(
        db=current_db(), read_file=read_then_delete, process=rec
    )
    assert rec.calls == [] and summary["requeued"] == 0


# ------------------------------------------------------------------ reprocess resets the budget


async def test_reprocess_gives_the_document_a_fresh_recovery_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def no_pipeline(*_: Any, **__: Any) -> None:
        return None

    monkeypatch.setattr("app.features.documents.router._run_pipeline_and_update", no_pipeline)
    user = await make_user()
    doc = await make_document(user["_id"], recoveryAttempts=1)
    with TestClient(app, raise_server_exceptions=False) as client:
        r = client.post(f"/api/documents/{doc['id']}/reprocess", headers=user["headers"])
    assert r.status_code == 202
    assert (await _doc(doc["_id"]))["recoveryAttempts"] == 0


# ------------------------------------------------------------------ startup never blocks


async def test_startup_and_health_are_not_blocked_by_a_slow_recovery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started = asyncio.Event()
    cancelled: list[bool] = []

    async def very_slow_recovery() -> dict[str, int]:
        started.set()
        try:
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            cancelled.append(True)
            raise
        return {}

    monkeypatch.setattr(settings, "recover_interrupted_uploads", True)
    monkeypatch.setattr("app.main.recover_interrupted_documents", very_slow_recovery)

    begin = time.perf_counter()
    with TestClient(app, raise_server_exceptions=False) as client:
        startup_seconds = time.perf_counter() - begin
        t0 = time.perf_counter()
        health = client.get("/health")
        health_seconds = time.perf_counter() - t0
        task = app.state.recovery_task
        assert task is not None and not task.done()  # recovery really is still running
    assert startup_seconds < 5, f"startup waited for recovery ({startup_seconds:.1f}s)"
    assert health.status_code == 200 and health_seconds < 1.0
    assert cancelled == [True]  # shutdown cancelled it cleanly instead of hanging for 30 s


async def test_a_crashing_recovery_does_not_break_startup(monkeypatch: pytest.MonkeyPatch) -> None:
    async def boom() -> dict[str, int]:
        raise RuntimeError("recovery blew up")

    monkeypatch.setattr(settings, "recover_interrupted_uploads", True)
    monkeypatch.setattr("app.main.recover_interrupted_documents", boom)
    with TestClient(app, raise_server_exceptions=False) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/api/auth/me").status_code == 401  # normal request handling intact


async def test_recovery_can_be_switched_off(monkeypatch: pytest.MonkeyPatch) -> None:
    called: list[bool] = []

    async def spy() -> dict[str, int]:
        called.append(True)
        return {}

    monkeypatch.setattr(settings, "recover_interrupted_uploads", False)
    monkeypatch.setattr("app.main.recover_interrupted_documents", spy)
    with TestClient(app, raise_server_exceptions=False) as client:
        assert client.get("/health").status_code == 200
        assert app.state.recovery_task is None
    assert called == []


async def test_startup_really_requeues_a_stuck_document_end_to_end(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = await make_user()
    doc = await _stuck(owner["_id"])
    rec = Recorder()
    monkeypatch.setattr(settings, "recover_interrupted_uploads", True)
    monkeypatch.setattr("app.features.documents.router._run_pipeline_and_update", rec)
    with TestClient(app, raise_server_exceptions=False):
        deadline = time.perf_counter() + 15
        while not rec.calls and time.perf_counter() < deadline:
            await asyncio.sleep(0.1)
    assert [c["id"] for c in rec.calls] == [doc["_id"]]
    assert rec.calls[0]["p1"] == PART1_BYTES and rec.calls[0]["p2"] == PART2_BYTES


def test_the_attempt_limit_is_two() -> None:
    assert recovery.MAX_RECOVERY_ATTEMPTS == 2


@pytest.fixture(autouse=True)
def _recovery_off_unless_asked(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setattr(settings, "recover_interrupted_uploads", False)
    yield
