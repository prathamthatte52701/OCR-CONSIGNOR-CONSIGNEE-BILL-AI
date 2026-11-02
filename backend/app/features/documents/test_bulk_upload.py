"""Bulk upload (up to 5 sets of Part 1 + Part 2). Tiny synthetic bytes only; the OCR pipeline is
replaced by a recorder. The rate-limit test is LAST: its TestClients shut the app down on exit."""

from collections.abc import Iterator
from typing import Any

import pytest
from bson import ObjectId
from fastapi.testclient import TestClient

from app.core.rate_limit import limiter
from app.features.documents import router as r_mod
from app.features.documents.router import MAX_BULK_SETS, MAX_FILE_SIZE
from app.main import app
from testkit import current_db, make_user

JPEG = b"\xff\xd8\xff"
URL = "/api/documents/bulk-upload"


def blob(tag: str, size: int = 100) -> bytes:
    return JPEG + tag.encode() + b"0" * (size - len(JPEG) - len(tag))


@pytest.fixture(scope="module")
def client() -> Iterator[TestClient]:
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


@pytest.fixture(autouse=True)
def pipeline_calls(monkeypatch: pytest.MonkeyPatch) -> list[ObjectId]:
    calls: list[ObjectId] = []

    async def fake_pipeline(doc_id: ObjectId, *_: Any, **__: Any) -> None:
        calls.append(doc_id)

    monkeypatch.setattr(r_mod, "_run_pipeline_and_update", fake_pipeline)
    return calls


def post(client: TestClient, user: dict[str, Any], sets: list[tuple[bytes, bytes]]) -> Any:
    files = []
    for i, (a, _) in enumerate(sets):
        files.append(("part1", (f"s{i}-p1.jpg", a, "image/jpeg")))
    for i, (_, b) in enumerate(sets):
        files.append(("part2", (f"s{i}-p2.jpg", b, "image/jpeg")))
    return client.post(URL, headers=user["headers"], files=files)


async def counts() -> tuple[int, int]:
    db = current_db()
    return await db.documents.count_documents({}), await db["fs.files"].count_documents({})


async def test_five_good_sets_store_ten_files_and_run_in_order(
    client: TestClient, pipeline_calls: list[ObjectId]
) -> None:
    user = await make_user()
    r = post(client, user, [(blob(f"a{i}"), blob(f"b{i}")) for i in range(5)])
    assert r.status_code == 201
    results = r.json()["results"]
    assert [x["index"] for x in results] == [0, 1, 2, 3, 4]
    ids = [x["id"] for x in results]
    assert await counts() == (5, 10)
    assert [str(c) for c in pipeline_calls] == ids
    for i, doc_id in enumerate(ids):  # set i keeps ITS two files
        d = client.get(f"/api/documents/{doc_id}/download/part1", headers=user["headers"])
        assert f"a{i}".encode() in d.content


async def test_bad_set_is_skipped_and_reported_others_go_through(
    client: TestClient, pipeline_calls: list[ObjectId]
) -> None:
    user = await make_user()
    sets = [(blob(f"a{i}"), blob(f"b{i}")) for i in range(5)]
    sets[2] = (sets[2][0], b"just text, not an image")
    r = post(client, user, sets)
    assert r.status_code == 201
    results = r.json()["results"]
    assert results[2]["index"] == 2 and "id" not in results[2]
    assert results[2]["error"].startswith("Set 3, Part 2")
    assert sum("id" in x for x in results) == 4
    assert await counts() == (4, 8)
    assert len(pipeline_calls) == 4


async def test_store_failure_on_set_2_rolls_back_only_that_set(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    real, n = r_mod.upload_buffer, []

    async def flaky(*a: Any, **k: Any) -> Any:
        n.append(1)
        if len(n) == 4:  # set 2's Part 2
            raise RuntimeError("gridfs down")
        return await real(*a, **k)

    monkeypatch.setattr(r_mod, "upload_buffer", flaky)
    user = await make_user()
    r = post(client, user, [(blob(f"a{i}"), blob(f"b{i}")) for i in range(3)])
    results = r.json()["results"]
    assert "id" in results[0] and "id" in results[2]
    assert results[1]["error"].startswith("Set 2,")
    assert await counts() == (2, 4)


async def test_pipeline_crash_on_set_2_marks_it_failed_and_set_3_still_runs(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    done: list[ObjectId] = []

    async def crashing(doc_id: ObjectId, *_: Any, **__: Any) -> None:
        if len(done) == 1:
            done.append(doc_id)
            raise RuntimeError("boom")
        done.append(doc_id)

    monkeypatch.setattr(r_mod, "_run_pipeline_and_update", crashing)
    user = await make_user()
    r = post(client, user, [(blob(f"a{i}"), blob(f"b{i}")) for i in range(3)])
    ids = [x["id"] for x in r.json()["results"]]
    assert [str(d) for d in done] == ids  # set 3 ran after set 2 crashed
    db = current_db()
    second = await db.documents.find_one({"_id": ObjectId(ids[1])})
    assert second["uploadStatus"] == "failed" and second["processingError"] == "RuntimeError"


async def test_real_pipeline_failure_on_set_2_does_not_stop_set_3(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.undo()  # drop the autouse recorder: this test runs the REAL update wrapper
    seen: list[int] = []

    async def pipeline(*_: Any) -> dict[str, Any]:
        seen.append(1)
        if len(seen) == 2:
            raise ValueError("ocr died")
        return {"invoiceNo": "X"}

    monkeypatch.setattr(r_mod, "run_full_pipeline", pipeline)
    user = await make_user()
    ids = [
        x["id"]
        for x in post(client, user, [(blob(f"a{i}"), blob(f"b{i}")) for i in range(3)]).json()[
            "results"
        ]
    ]
    status = [
        (await current_db().documents.find_one({"_id": ObjectId(i)}))["uploadStatus"] for i in ids
    ]
    assert status == ["processed", "failed", "processed"]


async def test_set_count_and_shape_guards(client: TestClient) -> None:
    user = await make_user()
    r = post(client, user, [(blob(f"a{i}"), blob(f"b{i}")) for i in range(MAX_BULK_SETS + 1)])
    assert r.status_code == 400
    unequal = client.post(
        URL,
        headers=user["headers"],
        files=[
            ("part1", ("a.jpg", blob("a"), "image/jpeg")),
            ("part1", ("b.jpg", blob("b"), "image/jpeg")),
            ("part2", ("c.jpg", blob("c"), "image/jpeg")),
        ],
    )
    assert unequal.status_code == 400
    assert unequal.json()["detail"] == "Each set needs both Part 1 and Part 2."
    assert client.post(URL, headers=user["headers"]).status_code == 400
    assert await counts() == (0, 0)


async def test_one_file_over_5mb_fails_only_its_set(client: TestClient) -> None:
    user = await make_user()
    big = blob("big", MAX_FILE_SIZE + 1)
    r = post(client, user, [(blob("a0"), blob("b0")), (big, blob("b1")), (blob("a2"), blob("b2"))])
    results = r.json()["results"]
    assert "id" in results[0] and "id" in results[2]
    assert results[1]["error"].startswith("Set 2, Part 1")
    assert await counts() == (2, 4)


async def test_other_users_documents_are_untouched(client: TestClient) -> None:
    owner, other = await make_user(), await make_user()
    mine = post(client, owner, [(blob("a"), blob("b"))]).json()["results"][0]["id"]
    post(client, other, [(blob("c"), blob("d"))])
    assert client.get(f"/api/documents/{mine}", headers=other["headers"]).status_code == 404
    assert await current_db().documents.count_documents({"userId": ObjectId(owner["id"])}) == 1


async def test_request_above_the_bulk_ceiling_is_413(client: TestClient) -> None:
    user = await make_user()
    too_big = MAX_BULK_SETS * 2 * MAX_FILE_SIZE + 1024 * 1024 + 1
    r = client.post(
        URL,
        headers={
            **user["headers"],
            "content-length": str(too_big),
            "content-type": "multipart/form-data; boundary=B",
        },
        content=b"x",
    )
    assert r.status_code == 413 and "Each file" in r.json()["detail"]


async def test_audit_log_failure_never_loses_a_set(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, pipeline_calls: list[ObjectId]
) -> None:
    async def broken_log(*_: Any, **__: Any) -> None:
        raise RuntimeError("audit down")

    monkeypatch.setattr(r_mod, "log_action", broken_log)
    user = await make_user()
    r = post(client, user, [(blob(f"a{i}"), blob(f"b{i}")) for i in range(3)])
    assert r.status_code == 201
    assert all("id" in x for x in r.json()["results"])
    assert await counts() == (3, 6)
    assert len(pipeline_calls) == 3


async def test_unexpected_error_in_set_2_is_reported_and_others_go_on(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, pipeline_calls: list[ObjectId]
) -> None:
    real, n = r_mod._store_upload, []

    async def sometimes_broken(*a: Any, **k: Any) -> Any:
        n.append(1)
        if len(n) == 2:
            raise RuntimeError("secret detail that must not leak")
        return await real(*a, **k)

    monkeypatch.setattr(r_mod, "_store_upload", sometimes_broken)
    user = await make_user()
    r = post(client, user, [(blob(f"a{i}"), blob(f"b{i}")) for i in range(3)])
    assert r.status_code == 201
    results = r.json()["results"]
    assert results[1]["error"] == "Set 2, Upload failed. Please try again."
    assert "id" in results[0] and "id" in results[2]
    assert len(pipeline_calls) == 2


async def test_ocr_calls_of_concurrent_jobs_never_overlap_and_a_crash_does_not_block(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Three jobs started together go through the REAL wrapper and the real OCR slot; the fake
    engine call counts how many threads run it at once."""
    import asyncio
    import threading
    import time

    from app.features.documents import processing
    from app.features.ocr.ocr_slot import run_in_ocr_slot

    guard, state = threading.Lock(), {"now": 0, "peak": 0, "calls": 0}

    def engine() -> list[Any]:
        with guard:
            state["calls"] += 1
            first = state["calls"] == 1
            state["now"] += 1
            state["peak"] = max(state["peak"], state["now"])
        try:
            time.sleep(0.05)
            if first:
                raise RuntimeError("ocr crashed")
            return []
        finally:
            with guard:
                state["now"] -= 1

    async def fake_part1(*_: Any) -> dict[str, Any]:
        await run_in_ocr_slot(engine, timeout=5)
        return {}

    async def fake_part2(*_: Any) -> dict[str, Any]:
        return {"lineItems": []}

    class _Docs:
        @staticmethod
        async def update_one(*_: Any, **__: Any) -> None:
            return None

    class _Db:
        documents = _Docs

    monkeypatch.undo()  # drop the autouse recorder: run the REAL wrapper
    monkeypatch.setattr(processing, "process_part1", fake_part1)
    monkeypatch.setattr(processing, "process_part2", fake_part2)
    monkeypatch.setattr(r_mod, "get_database", lambda: _Db())
    args = (b"a", "image/jpeg", b"b", "image/jpeg")
    await asyncio.gather(
        *(r_mod._run_pipeline_and_update(ObjectId(), *args, is_reprocess=False) for _ in range(3))
    )
    assert state["calls"] == 3 and state["peak"] == 1  # job 1 crashed; jobs 2 and 3 still ran


# Last on purpose: its own TestClient contexts shut the app (and its db) down on exit.
async def test_31st_bulk_request_is_429_and_single_upload_is_unaffected() -> None:
    limiter.reset()
    user = await make_user()
    h = user["headers"]
    with TestClient(app, raise_server_exceptions=False, client=("10.0.0.1", 5000)) as c1:
        for _ in range(30):
            assert c1.post(URL, headers=h).status_code == 400
        assert c1.post(URL, headers=h).status_code == 429
        single = c1.post(
            "/api/documents/upload",
            headers=h,
            files={"part1": ("a.jpg", b"", "image/jpeg"), "part2": ("b.jpg", b"x", "image/jpeg")},
        )
        assert single.status_code == 400  # reached the route: not limited
