"""Download All: POST {documentIds} -> zip of the originals of exactly those documents."""

import io
import os
import threading
import zipfile
from typing import Any

import pytest
from bson import ObjectId
from fastapi.testclient import TestClient

from app.features.documents import router as r_mod
from app.main import app
from testkit import PART1_BYTES, PART2_BYTES, current_db, make_document, make_user

URL = "/api/documents/download-all"


@pytest.fixture(scope="module")
def client() -> Any:
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


@pytest.fixture(autouse=True)
def _free_slots() -> Any:
    r_mod._active_downloads.clear()
    yield
    r_mod._active_downloads.clear()


def post(client: TestClient, user: dict[str, Any], ids: list[str]) -> Any:
    return client.post(URL, json={"documentIds": ids}, headers=user["headers"])


def names(resp: Any) -> set[str]:
    return set(zipfile.ZipFile(io.BytesIO(resp.content)).namelist())


async def test_zip_has_one_folder_per_document(client: TestClient) -> None:
    u = await make_user()
    a = await make_document(u["_id"], invoiceNo="ZIP-A")
    b = await make_document(u["_id"], invoiceNo="ZIP-B")
    r = post(client, u, [a["id"], b["id"]])
    assert r.status_code == 200
    assert (r.headers["X-Included-Count"], r.headers["X-Skipped-Count"]) == ("2", "0")
    assert r.headers["X-Total-Count"] == "2"
    assert names(r) == {
        "ZIP-A/part1_part1.jpg",
        "ZIP-A/part2_part2.jpg",
        "ZIP-B/part1_part1.jpg",
        "ZIP-B/part2_part2.jpg",
    }
    zf = zipfile.ZipFile(io.BytesIO(r.content))
    assert zf.read("ZIP-A/part1_part1.jpg") == PART1_BYTES
    assert zf.read("ZIP-A/part2_part2.jpg") == PART2_BYTES


async def test_more_than_30_ids_is_400(client: TestClient) -> None:
    u = await make_user()
    assert post(client, u, [str(ObjectId()) for _ in range(31)]).status_code == 400
    assert post(client, u, [str(ObjectId()) for _ in range(30)]).status_code == 200


async def test_duplicate_ids_are_deduplicated_in_order(client: TestClient) -> None:
    u = await make_user()
    a = await make_document(u["_id"], invoiceNo="DUP-1")
    r = post(client, u, [a["id"], a["id"]])
    assert r.headers["X-Included-Count"] == "1" and r.headers["X-Total-Count"] == "2"


async def test_foreign_and_deleted_ids_are_skipped_and_counted(client: TestClient) -> None:
    u, other = await make_user(), await make_user()
    mine = await make_document(u["_id"], invoiceNo="MINE")
    theirs = await make_document(other["_id"], invoiceNo="THEIRS")
    gone = await make_document(u["_id"], invoiceNo="GONE", isDeleted=True)
    r = post(client, u, [mine["id"], theirs["id"], gone["id"], str(ObjectId())])
    assert r.status_code == 200
    assert (r.headers["X-Included-Count"], r.headers["X-Skipped-Count"]) == ("1", "3")
    assert names(r) == {"MINE/part1_part1.jpg", "MINE/part2_part2.jpg"}


async def test_malformed_id_is_400(client: TestClient) -> None:
    u = await make_user()
    assert post(client, u, ["nope"]).status_code == 400


async def test_same_invoice_number_gets_unique_folders(client: TestClient) -> None:
    u = await make_user()
    ids = [(await make_document(u["_id"], invoiceNo="SAME"))["id"] for _ in range(3)]
    r = post(client, u, ids)
    assert r.headers["X-Included-Count"] == "3"
    folders = {n.split("/")[0] for n in names(r)}
    assert folders == {"SAME", "SAME-2", "SAME-3"} and len(names(r)) == 6


async def test_hostile_invoice_number_cannot_escape_the_zip(client: TestClient) -> None:
    u = await make_user()
    d = await make_document(u["_id"], invoiceNo="../../etc/passwd")
    for n in names(post(client, u, [d["id"]])):
        assert not n.startswith(("/", "..")) and ".." not in n.split("/")


async def test_purged_missing_and_unreadable_parts_are_skipped(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    u = await make_user()
    good = await make_document(u["_id"], invoiceNo="GOOD")
    purged = await make_document(u["_id"], invoiceNo="PURGED", part1FilePurged=True)
    no_id = await make_document(u["_id"], invoiceNo="NOID", part2GridFsFileId=None)
    broken = await make_document(u["_id"], invoiceNo="BROKEN")
    real = r_mod.download_buffer

    async def flaky(file_id: ObjectId) -> bytes:
        if file_id == broken["part2GridFsFileId"]:
            raise RuntimeError("gridfs down")
        return await real(file_id)

    monkeypatch.setattr(r_mod, "download_buffer", flaky)
    r = post(client, u, [good["id"], purged["id"], no_id["id"], broken["id"]])
    assert r.status_code == 200
    assert (r.headers["X-Included-Count"], r.headers["X-Skipped-Count"]) == ("1", "3")
    assert {n.split("/")[0] for n in names(r)} == {"GOOD"}  # no half-written BROKEN folder


async def test_over_the_size_cap_is_413_before_any_read(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    u = await make_user()
    a = await make_document(u["_id"], part1Size=600, part2Size=600)
    reads: list[Any] = []

    async def spy(file_id: ObjectId) -> bytes:
        reads.append(file_id)
        return b""

    monkeypatch.setattr(r_mod, "MAX_DOWNLOAD_ALL_BYTES", 1000)
    monkeypatch.setattr(r_mod, "download_buffer", spy)
    r = post(client, u, [a["id"]])
    assert r.status_code == 413 and "too large" in r.json()["detail"] and reads == []
    assert r_mod._active_downloads == {}  # slot freed after the error


async def test_size_falls_back_to_the_gridfs_length(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    u = await make_user()
    a = await make_document(u["_id"])  # no part1Size / part2Size stored
    monkeypatch.setattr(r_mod, "MAX_DOWNLOAD_ALL_BYTES", len(PART1_BYTES) + len(PART2_BYTES) - 1)
    assert post(client, u, [a["id"]]).status_code == 413
    monkeypatch.setattr(r_mod, "MAX_DOWNLOAD_ALL_BYTES", len(PART1_BYTES) + len(PART2_BYTES))
    assert post(client, u, [a["id"]]).status_code == 200


async def test_second_download_while_one_runs_is_429_and_slot_is_freed(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    u = await make_user()
    a = await make_document(u["_id"], invoiceNo="SLOW")
    started, release = threading.Event(), threading.Event()
    real = r_mod.download_buffer

    async def slow(file_id: ObjectId) -> bytes:
        started.set()
        while not release.is_set():
            await r_mod.asyncio.sleep(0.02)
        return await real(file_id)

    monkeypatch.setattr(r_mod, "download_buffer", slow)
    first: list[Any] = []
    t = threading.Thread(target=lambda: first.append(post(client, u, [a["id"]])))
    t.start()
    assert started.wait(10)
    assert post(client, u, [a["id"]]).status_code == 429
    release.set()
    t.join(20)
    assert first[0].status_code == 200
    assert r_mod._active_downloads == {}
    monkeypatch.setattr(r_mod, "download_buffer", real)
    assert post(client, u, [a["id"]]).status_code == 200  # slot is free again


async def test_slot_is_freed_when_building_the_zip_fails(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    u = await make_user()
    a = await make_document(u["_id"])

    def broken_mkstemp(**_: Any) -> Any:
        raise OSError("disk full")

    monkeypatch.setattr(r_mod.tempfile, "mkstemp", broken_mkstemp)
    assert post(client, u, [a["id"]]).status_code == 500
    assert r_mod._active_downloads == {}


async def test_temp_file_is_removed_after_the_download(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    u = await make_user()
    a = await make_document(u["_id"])
    paths: list[str] = []
    real = r_mod.tempfile.mkstemp

    def spy(**kwargs: Any) -> Any:
        fd, path = real(**kwargs)
        paths.append(path)
        return fd, path

    monkeypatch.setattr(r_mod.tempfile, "mkstemp", spy)
    assert post(client, u, [a["id"]]).status_code == 200
    assert len(paths) == 1 and not os.path.exists(paths[0])


async def test_audit_row_is_written_and_a_failing_audit_does_not_fail_the_download(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    u = await make_user()
    a = await make_document(u["_id"])
    gone = str(ObjectId())
    assert post(client, u, [a["id"], gone]).status_code == 200
    row = await current_db().auditlogs.find_one(
        {"action": "documents_download_all", "userId": u["_id"]}
    )
    assert row is not None
    assert row["context"] == {"requested": 2, "included": 1, "skipped": 1}

    async def boom(*_: Any, **__: Any) -> None:
        raise RuntimeError("audit down")

    monkeypatch.setattr(r_mod, "log_action", boom)
    r = post(client, u, [a["id"]])
    assert r.status_code == 200 and r.headers["X-Included-Count"] == "1"
