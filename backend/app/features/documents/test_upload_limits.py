"""T10: upload size limits (declared Content-Length, streamed body, and a per-file cap enforced
while reading - for BOTH parts), the existing type checks, and hostile filenames.

Uses tiny synthetic bytes (a JPEG magic number plus padding) - never a real document, and the
OCR pipeline is replaced by a no-op."""

import io
import zipfile
from collections.abc import Iterator
from typing import Any

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


@pytest.mark.parametrize("magic", [JPEG, PNG, PDF])
async def test_all_three_allowed_types_pass(client: TestClient, magic: bytes) -> None:
    user = await make_user()
    assert _upload(client, user, blob(64, magic), blob(64, magic)).status_code == 201


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
