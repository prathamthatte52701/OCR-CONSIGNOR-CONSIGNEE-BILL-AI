"""T10: upload size limits (declared Content-Length, streamed body, and a per-file cap enforced
while reading - for BOTH parts), the existing type checks, and hostile filenames.

Uses tiny synthetic bytes (a JPEG magic number plus padding) - never a real document, and the
OCR pipeline is replaced by a no-op."""

import io
import struct
import zipfile
import zlib
from collections.abc import Iterator
from typing import Any

import fitz
import pytest
from fastapi.testclient import TestClient

from app.features.documents.router import MAX_FILE_SIZE
from app.main import app
from testkit import current_db, make_document, make_user

JPEG = b"\xff\xd8\xff"
PNG = b"\x89PNG\r\n\x1a\n"
PDF = b"%PDF-1.4\n"


def blob(size: int, magic: bytes = JPEG) -> bytes:
    return magic + b"0" * (size - len(magic))


@pytest.fixture(scope="module")
def client() -> Iterator[TestClient]:
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


@pytest.fixture(autouse=True)
def _no_real_pipeline(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_pipeline(*_: Any, **__: Any) -> None:
        return None

    monkeypatch.setattr("app.features.documents.router._run_pipeline_and_update", fake_pipeline)


def _upload(
    client: TestClient,
    user: dict[str, Any],
    part1: bytes,
    part2: bytes,
    names: tuple[str, str] = ("a.jpg", "b.jpg"),
) -> Any:
    return client.post(
        "/api/documents/upload",
        headers=user["headers"],
        files={"part1": (names[0], part1, "image/jpeg"), "part2": (names[1], part2, "image/jpeg")},
    )


async def _stored() -> tuple[int, int]:
    db = current_db()
    return await db.documents.count_documents({}), await db["fs.files"].count_documents({})


async def test_small_valid_upload_is_accepted_and_stored(client: TestClient) -> None:
    user = await make_user()
    r = _upload(client, user, blob(100), blob(100, PNG))
    assert r.status_code == 201 and r.json()["uploadStatus"] == "processing"
    assert await _stored() == (1, 2)


async def test_files_of_exactly_the_maximum_size_are_accepted(client: TestClient) -> None:
    user = await make_user()
    r = _upload(client, user, blob(MAX_FILE_SIZE), blob(MAX_FILE_SIZE))
    assert r.status_code == 201, r.text[:200]
    assert await _stored() == (1, 2)


async def test_part1_one_byte_over_is_refused_and_nothing_is_stored(client: TestClient) -> None:
    user = await make_user()
    r = _upload(client, user, blob(MAX_FILE_SIZE + 1), blob(100))
    assert r.status_code == 400 and r.json()["detail"] == "Part 1 file exceeds the 5MB limit."
    assert await _stored() == (0, 0)


async def test_part2_one_byte_over_is_refused_and_part1_is_not_kept(client: TestClient) -> None:
    user = await make_user()
    r = _upload(client, user, blob(100), blob(MAX_FILE_SIZE + 1))
    assert r.status_code == 400 and r.json()["detail"] == "Part 2 file exceeds the 5MB limit."
    assert await _stored() == (0, 0)  # the valid Part 1 must not be left behind


async def test_both_oversized_reports_part1_first(client: TestClient) -> None:
    user = await make_user()
    r = _upload(client, user, blob(MAX_FILE_SIZE + 10), blob(MAX_FILE_SIZE + 10))
    assert r.status_code == 400 and "Part 1" in r.json()["detail"]
    assert await _stored() == (0, 0)


async def test_request_above_the_whole_body_ceiling_is_413(client: TestClient) -> None:
    user = await make_user()
    big = blob(5 * 1024 * 1024 + 700_000)  # two of these exceed 2 x 5 MB + 1 MB framing allowance
    r = _upload(client, user, big, big)
    assert r.status_code == 413 and r.json() == {"detail": "Each file must be 5 MB or less."}
    assert await _stored() == (0, 0)


async def test_chunked_upload_without_content_length_is_cut_off(client: TestClient) -> None:
    user = await make_user()

    def body() -> Iterator[bytes]:
        yield b'--B\r\nContent-Disposition: form-data; name="part1"; filename="a.jpg"\r\n'
        yield b"Content-Type: image/jpeg\r\n\r\n" + JPEG
        for _ in range(12 * 16):  # ~12 MB streamed
            yield b"0" * 64 * 1024
        yield b"\r\n--B--\r\n"

    r = client.post(
        "/api/documents/upload",
        content=body(),
        headers={**user["headers"], "Content-Type": "multipart/form-data; boundary=B"},
    )
    assert r.status_code == 413
    assert await _stored() == (0, 0)


@pytest.mark.parametrize(
    ("part1", "part2", "message"),
    [
        (b"", blob(50), "Part 1 file is empty."),
        (blob(50), b"", "Part 2 file is empty."),
        (b"plain text, not an image" * 4, blob(50), "Part 1 file type not supported."),
        (blob(50), b"GIF89a" + b"0" * 50, "Part 2 file type not supported."),
        (b"MZ\x90\x00" + b"0" * 50, blob(50), "Part 1 file type not supported."),
    ],
)
async def test_existing_empty_and_type_checks_still_apply(
    client: TestClient, part1: bytes, part2: bytes, message: str
) -> None:
    user = await make_user()
    r = _upload(client, user, part1, part2)
    assert r.status_code == 400 and r.json()["detail"] == message
    assert await _stored() == (0, 0)


async def test_a_file_named_jpg_but_not_a_jpeg_is_rejected_by_content(client: TestClient) -> None:
    user = await make_user()
    r = _upload(client, user, b"<?php system($_GET['x']); ?>" * 3, blob(50), ("shell.jpg", "b.jpg"))
    assert r.status_code == 400


async def test_missing_part_is_422(client: TestClient) -> None:
    user = await make_user()
    r = client.post(
        "/api/documents/upload",
        headers=user["headers"],
        files={"part1": ("a.jpg", blob(50), "image/jpeg")},
    )
    assert r.status_code == 422
    assert r.json()["detail"][0]["msg"] == "Part 2 is required."
    assert set(r.json()["detail"][0]) == {"loc", "msg", "type"}


# ------------------------------------------------------------------ hostile filenames


@pytest.mark.parametrize(
    "hostile",
    ["../../etc/passwd.jpg", 'a"b.jpg', "C:\\Windows\\x.jpg", "हिन्दी.jpg", "x" * 300 + ".jpg", ""],
)
async def test_hostile_upload_filenames_are_stored_safely_and_downloads_work(
    client: TestClient, hostile: str
) -> None:
    user = await make_user()
    r = _upload(client, user, blob(50), blob(50), (hostile or "blank.jpg", "ok.jpg"))
    assert r.status_code == 201
    stored = await current_db().documents.find_one({})
    assert stored is not None
    name = stored["part1OriginalFilename"]
    assert name.isascii() and "/" not in name and "\\" not in name and '"' not in name
    assert ".." not in name.split(".")[0] or name == "passwd.jpg"
    dl = client.get(f"/api/documents/{r.json()['id']}/download/part1", headers=user["headers"])
    assert dl.status_code == 200
    assert dl.headers["content-disposition"].count('"') == 2


async def test_legacy_documents_with_hostile_stored_names_cannot_break_downloads(
    client: TestClient,
) -> None:
    user = await make_user()
    doc = await make_document(
        user["_id"],
        part1OriginalFilename='evil"\r\nSet-Cookie: pwned=1\r\n\r\n<script>.jpg',
        part2OriginalFilename="हिन्दी.jpg",
    )
    for part in ("part1", "part2"):
        r = client.get(f"/api/documents/{doc['id']}/download/{part}", headers=user["headers"])
        assert r.status_code == 200  # (an encode error here used to be a 500)
        header = r.headers["content-disposition"]
        assert header.count('"') == 2 and "set-cookie" not in {k.lower() for k in r.headers}


async def test_zip_entries_cannot_escape_the_extraction_folder(client: TestClient) -> None:
    user = await make_user()
    await make_document(
        user["_id"],
        invoiceNo="../../../evil",
        part1OriginalFilename="../../../../etc/cron.d/x.jpg",
        part2OriginalFilename="/abs/path/y.jpg",
    )
    await make_document(user["_id"], invoiceNo="..\\..\\win", part1OriginalFilename="..\\z.jpg")
    r = client.post("/api/documents/download-all", headers=user["headers"])
    assert r.status_code == 200 and int(r.headers["x-included-count"]) == 2
    names = zipfile.ZipFile(io.BytesIO(r.content)).namelist()
    assert len(names) == 4
    for name in names:
        assert not name.startswith("/") and "\\" not in name and ".." not in name.split("/")
        assert name.count("/") == 1  # exactly folder/file, never deeper or higher


# ------------------------------------------------------------------ ACKN upload rules (B1-B6)


def real_pdf(pages: int = 1) -> bytes:
    doc = fitz.open()
    for _ in range(pages):
        doc.new_page()
    return bytes(doc.tobytes())


def png_header(width: int, height: int) -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        crc = struct.pack(">I", zlib.crc32(kind + data))
        return struct.pack(">I", len(data)) + kind + data + crc

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0)
    return PNG + chunk(b"IHDR", ihdr) + chunk(b"IDAT", b"x" * 8)


def _pdf_with_mediabox(box: str) -> bytes:
    return (
        "%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        "2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
        f"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[{box}]>>endobj\n"
        "trailer<</Root 1 0 R>>\n%%EOF"
    ).encode()


def _pair(bad_part: int, good: bytes, bad: bytes) -> tuple[bytes, bytes]:
    return (bad, good) if bad_part == 1 else (good, bad)


@pytest.mark.parametrize("data", [blob(64, JPEG), blob(64, PNG), real_pdf()])
async def test_pdf_and_images_pass(client: TestClient, data: bytes) -> None:
    user = await make_user()
    assert _upload(client, user, data, data).status_code == 201


@pytest.mark.parametrize("bad_part", [1, 2])
async def test_valid_part_plus_invalid_part_stores_nothing(
    client: TestClient, bad_part: int
) -> None:
    user = await make_user()
    r = _upload(client, user, *_pair(bad_part, blob(100), b"MZ" + b"0" * 50))
    assert r.status_code == 400 and f"Part {bad_part}" in r.json()["detail"]
    assert await _stored() == (0, 0)


@pytest.mark.parametrize("bad_part", [1, 2])
async def test_five_page_pdf_is_refused(client: TestClient, bad_part: int) -> None:
    user = await make_user()
    r = _upload(client, user, *_pair(bad_part, blob(100), real_pdf(5)))
    assert r.status_code == 400
    assert r.json()["detail"] == f"Part {bad_part}: PDF must be 4 pages or less."
    assert await _stored() == (0, 0)


async def test_four_page_pdf_is_accepted(client: TestClient) -> None:
    user = await make_user()
    assert _upload(client, user, real_pdf(4), blob(100)).status_code == 201


async def test_unreadable_pdf_is_refused(client: TestClient) -> None:
    user = await make_user()
    r = _upload(client, user, blob(100), blob(100, PDF))
    assert r.status_code == 400
    assert r.json()["detail"] == (
        "Part 2: Could not read this PDF. Please upload a valid PDF or convert it to JPG/PNG."
    )
    assert await _stored() == (0, 0)


async def test_huge_pixel_image_is_refused(client: TestClient) -> None:
    user = await make_user()
    r = client.post(
        "/api/documents/upload",
        headers=user["headers"],
        files={
            "part1": ("a.png", png_header(14000, 14000), "image/png"),
            "part2": ("b.jpg", blob(100), "image/jpeg"),
        },
    )
    assert r.status_code == 400
    assert r.json()["detail"].startswith("Part 1: This image is too large")
    assert await _stored() == (0, 0)


async def test_huge_pdf_page_is_refused(client: TestClient) -> None:
    user = await make_user()
    r = _upload(client, user, blob(100), _pdf_with_mediabox("0 0 14400 14400"))
    assert r.status_code == 400
    assert r.json()["detail"].startswith("Part 2: This PDF page is too large")
    assert await _stored() == (0, 0)


async def test_every_validation_error_names_the_part(client: TestClient) -> None:
    user = await make_user()
    cases = [
        (b"", blob(50)),
        (blob(50), b"GIF89a" + b"0" * 50),
        (real_pdf(5), blob(50)),
        (blob(50), blob(50, PDF)),
        (blob(MAX_FILE_SIZE + 1), blob(50)),
        (blob(50), png_header(14000, 14000)),
    ]
    for p1, p2 in cases:
        detail = _upload(client, user, p1, p2).json()["detail"]
        assert "Part 1" in detail or "Part 2" in detail, detail


async def test_413_message_says_each_file(client: TestClient) -> None:
    user = await make_user()
    big = blob(5 * 1024 * 1024 + 700_000)
    assert "Each file" in _upload(client, user, big, big).json()["detail"]


class _BrokenDb:
    class documents:  # noqa: N801
        @staticmethod
        async def insert_one(*_: Any, **__: Any) -> Any:
            raise RuntimeError("insert failed")

        @staticmethod
        async def find_one(*_: Any, **__: Any) -> Any:
            return None  # the lost-ack lookup: no document exists, so the files are rolled back


async def test_part2_store_failure_deletes_part1(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.features.documents import router as r_mod

    real_upload, calls = r_mod.upload_buffer, []

    async def flaky(*a: Any, **k: Any) -> Any:
        calls.append(1)
        if len(calls) == 2:
            raise RuntimeError("gridfs down")
        return await real_upload(*a, **k)

    monkeypatch.setattr(r_mod, "upload_buffer", flaky)
    user = await make_user()
    r = _upload(client, user, blob(100), blob(100))
    assert r.status_code == 500 and r.json()["detail"] == "Upload failed. Please try again."
    assert await _stored() == (0, 0)


async def test_insert_failure_deletes_both_files(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.features.documents import router as r_mod

    monkeypatch.setattr(r_mod, "get_database", lambda: _BrokenDb())
    user = await make_user()
    r = _upload(client, user, blob(100), blob(100))
    assert r.status_code == 500 and r.json()["detail"] == "Upload failed. Please try again."
    assert await current_db()["fs.files"].count_documents({}) == 0


async def test_failed_rollback_delete_records_orphans(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.features.documents import router as r_mod

    async def no_delete(_: Any) -> None:
        raise RuntimeError("delete failed")

    monkeypatch.setattr(r_mod, "get_database", lambda: _BrokenDb())
    monkeypatch.setattr(r_mod, "delete_file", no_delete)
    user = await make_user()
    assert _upload(client, user, blob(100), blob(100)).status_code == 500
    assert await current_db().orphanedfiles.count_documents({}) == 2


class _AckLostDb:
    """Real db, but insert_one commits and then raises (the acknowledgement was lost)."""

    def __init__(self, real: Any, lookup_fails: bool = False) -> None:
        self.documents = self
        self._real, self._lookup_fails = real.documents, lookup_fails

    async def insert_one(self, doc: Any) -> Any:
        await self._real.insert_one(doc)
        raise RuntimeError("ack lost")

    async def find_one(self, *a: Any, **k: Any) -> Any:
        if self._lookup_fails:
            raise RuntimeError("lookup down")
        return await self._real.find_one(*a, **k)


async def test_lost_insert_ack_keeps_files_and_succeeds(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.core.database import get_database
    from app.features.documents import router as r_mod

    monkeypatch.setattr(r_mod, "get_database", lambda: _AckLostDb(get_database()))
    user = await make_user()
    r = _upload(client, user, blob(100), blob(100))
    assert r.status_code == 201
    assert await _stored() == (1, 2)
    doc = await current_db().documents.find_one({})
    assert str(doc["_id"]) == r.json()["id"]


async def test_lost_ack_and_failed_lookup_deletes_nothing_records_nothing(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.core.database import get_database
    from app.features.documents import router as r_mod

    monkeypatch.setattr(
        r_mod, "get_database", lambda: _AckLostDb(get_database(), lookup_fails=True)
    )
    user = await make_user()
    r = _upload(client, user, blob(100), blob(100))
    assert r.status_code == 500 and r.json()["detail"] == "Upload failed. Please try again."
    assert await _stored() == (1, 2)
    assert await current_db().orphanedfiles.count_documents({}) == 0


async def test_cancellation_during_stores_rolls_back_then_reraises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import asyncio

    from bson import ObjectId

    from app.features.documents import router as r_mod

    deleted: list[ObjectId] = []
    calls: list[int] = []

    async def cancelling_upload(*_: Any) -> ObjectId:
        calls.append(1)
        if len(calls) == 2:
            raise asyncio.CancelledError
        return ObjectId()

    async def fake_delete(file_id: ObjectId) -> None:
        deleted.append(file_id)

    monkeypatch.setattr(r_mod, "upload_buffer", cancelling_upload)
    monkeypatch.setattr(r_mod, "delete_file", fake_delete)
    monkeypatch.setattr(r_mod, "get_database", lambda: None)
    with pytest.raises(asyncio.CancelledError):
        await r_mod._store_upload(
            ObjectId(), ("a.jpg", b"x", "image/jpeg"), ("b.jpg", b"y", "image/jpeg")
        )
    assert len(deleted) == 1


async def test_failed_gridfs_write_sweeps_its_partial_chunks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GridFS does not abort a half-written upload itself; upload_buffer must delete by id."""
    from app.features.documents import gridfs_service as g

    deleted: list[Any] = []

    class _Bucket:
        async def upload_from_stream_with_id(self, file_id: Any, *_: Any, **__: Any) -> None:
            self.id = file_id
            raise RuntimeError("write died mid-way")

    async def fake_delete(file_id: Any) -> None:
        deleted.append(file_id)

    bucket = _Bucket()
    monkeypatch.setattr(g, "get_gridfs", lambda: bucket)
    monkeypatch.setattr(g, "delete_file", fake_delete)
    with pytest.raises(RuntimeError):
        await g.upload_buffer(b"x", "a.jpg", "image/jpeg")
    assert deleted == [bucket.id]


# ------------------------------------------------------------------ break-it (documenting)


async def test_same_file_in_both_slots_is_accepted_as_two_separate_files(
    client: TestClient,
) -> None:
    """Today's behaviour, no guard wanted: the same bytes in both slots store twice."""
    user = await make_user()
    data = blob(200)
    r = _upload(client, user, data, data)
    assert r.status_code == 201
    doc = await current_db().documents.find_one({})
    assert doc["part1GridFsFileId"] != doc["part2GridFsFileId"]
    assert await _stored() == (1, 2)


async def test_two_simultaneous_uploads_from_one_user_do_not_mix(client: TestClient) -> None:
    from concurrent.futures import ThreadPoolExecutor

    user = await make_user()
    pairs = [(blob(100) + b"A1", blob(100) + b"A2"), (blob(100) + b"B1", blob(100) + b"B2")]
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(lambda p: _upload(client, user, *p), pairs))
    assert [r.status_code for r in results] == [201, 201]
    docs = await current_db().documents.find({}).to_list(length=None)
    assert len(docs) == 2
    ids = {d["part1GridFsFileId"] for d in docs} | {d["part2GridFsFileId"] for d in docs}
    assert len(ids) == 4
    for d in docs:
        for part in ("part1", "part2"):
            dl = client.get(f"/api/documents/{d['_id']}/download/{part}", headers=user["headers"])
            tail = dl.content[-2:]
            assert tail[1:] == (b"1" if part == "part1" else b"2")
            assert tail[:1] in (b"A", b"B")
    # the two documents' parts come from the same pair, not crossed
    for d in docs:
        a = client.get(f"/api/documents/{d['_id']}/download/part1", headers=user["headers"])
        b = client.get(f"/api/documents/{d['_id']}/download/part2", headers=user["headers"])
        assert a.content[-2:-1] == b.content[-2:-1]


# Last on purpose: its own TestClient contexts shut the app (and its db) down on exit.
async def test_121st_upload_from_one_ip_is_429_other_ip_is_fine() -> None:
    user = await make_user()
    files = {"part1": ("a.jpg", b"", "image/jpeg"), "part2": ("b.jpg", blob(50), "image/jpeg")}
    url, h = "/api/documents/upload", user["headers"]
    with TestClient(app, raise_server_exceptions=False, client=("10.0.0.1", 5000)) as c1:
        for _ in range(120):
            assert c1.post(url, headers=h, files=files).status_code == 400
        assert c1.post(url, headers=h, files=files).status_code == 429
    with TestClient(app, raise_server_exceptions=False, client=("10.0.0.2", 5000)) as c2:
        assert c2.post(url, headers=h, files=files).status_code == 400
