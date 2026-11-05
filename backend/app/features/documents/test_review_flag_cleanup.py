"""Feature 7 fixes: review-warnings flag, temp-zip sweep, strict date param, total count."""

import os
import tempfile
import time
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.features.documents import router as r_mod
from app.main import app
from testkit import current_db, make_document, make_user

_REAL_JOB = r_mod._run_pipeline_and_update  # before any test stubs it
CLEAN: dict[str, Any] = {
    "totalBasicAmount": "100.00",
    "totalAmount": "100.00",
    "lineItems": [{"amount": "100.00"}],
    "multiPage": False,
}


@pytest.fixture(scope="module")
def client() -> Any:
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


async def flag(doc_id: Any) -> Any:
    row = await current_db().documents.find_one({"_id": doc_id})
    return row.get("hasReviewWarnings")


# ------------------------------------------------------------------ flag after processing


@pytest.mark.parametrize(("totals", "expected"), [({}, False), ({"totalAmount": "999.00"}, True)])
async def test_flag_is_set_when_processing_finishes(
    monkeypatch: pytest.MonkeyPatch, totals: dict[str, str], expected: bool
) -> None:
    async def pipeline(*_: Any) -> dict[str, Any]:
        return {**CLEAN, **totals, "hasLowConfidenceFields": False}

    monkeypatch.setattr(r_mod, "run_full_pipeline", pipeline)
    monkeypatch.setattr(r_mod, "get_database", current_db)
    user = await make_user()
    doc = await make_document(
        user["_id"], uploadStatus="processing", processingRunId="r1", hasReviewWarnings=not expected
    )
    await _REAL_JOB(
        doc["_id"], b"a", "image/jpeg", b"b", "image/jpeg", is_reprocess=True, run_id="r1"
    )
    assert await flag(doc["_id"]) is expected  # also on Reprocess, replacing the old value


# ------------------------------------------------------------------ flag after corrections


async def test_flag_is_recomputed_after_each_correction(client: TestClient) -> None:
    user = await make_user()
    doc = await make_document(user["_id"], hasReviewWarnings=False, **CLEAN)

    def correct(field: str, value: str) -> Any:
        return client.patch(
            f"/api/documents/{doc['id']}/correct",
            json={"field": field, "value": value},
            headers=user["headers"],
        )

    assert correct("totalAmount", "999.00").status_code == 200
    assert await flag(doc["_id"]) is True  # false -> true
    assert correct("totalAmount", "100.00").status_code == 200
    assert await flag(doc["_id"]) is False  # true -> false
    assert correct("lineItems.0.amount", "55.00").status_code == 200
    assert await flag(doc["_id"]) is True  # a line item edit counts too


# ------------------------------------------------------------------ needsReview


async def test_needs_review_finds_warning_only_documents(client: TestClient) -> None:
    user = await make_user()
    warn = await make_document(user["_id"], invoiceNo="WARN-1", hasReviewWarnings=True)
    other_warn = await make_document(user["_id"], invoiceNo="OTHER", hasReviewWarnings=True)
    clean = await make_document(user["_id"], invoiceNo="WARN-2", hasReviewWarnings=False)
    legacy = await make_document(user["_id"], invoiceNo="WARN-3")  # no field at all

    def ids(params: dict[str, str]) -> set[str]:
        r = client.get("/api/documents", params=params, headers=user["headers"])
        return {i["id"] for i in r.json()["items"]}

    assert ids({"needsReview": "true"}) == {warn["id"], other_warn["id"]}
    assert clean["id"] not in ids({"needsReview": "true"})
    assert legacy["id"] not in ids({"needsReview": "true"})
    assert ids({"needsReview": "true", "search": "warn-"}) == {warn["id"]}  # both conditions


# ------------------------------------------------------------------ temp zip sweep


def _temp_zip(name: str, age_minutes: float) -> str:
    path = os.path.join(tempfile.gettempdir(), name)
    with open(path, "wb") as f:
        f.write(b"x")
    old = time.time() - age_minutes * 60
    os.utime(path, (old, old))
    return path


async def test_sweep_removes_only_old_download_all_zips(client: TestClient) -> None:
    tag = os.urandom(4).hex()
    old = _temp_zip(f"download-all-{tag}-old.zip", 45)
    fresh = _temp_zip(f"download-all-{tag}-fresh.zip", 1)
    other = _temp_zip(f"unrelated-{tag}.zip", 45)
    wrong_ext = _temp_zip(f"download-all-{tag}.txt", 45)
    try:
        user = await make_user()
        r = client.post(
            "/api/documents/download-all", json={"documentIds": []}, headers=user["headers"]
        )
        assert r.status_code == 200
        assert not os.path.exists(old)
        assert os.path.exists(fresh) and os.path.exists(other) and os.path.exists(wrong_ext)
    finally:
        for p in (old, fresh, other, wrong_ext):
            if os.path.exists(p):
                os.unlink(p)


async def test_sweep_failure_does_not_fail_the_download(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom() -> None:
        raise RuntimeError("sweep exploded")

    monkeypatch.setattr(r_mod, "_sweep_old_temp_zips", boom)
    user = await make_user()
    r = client.post(
        "/api/documents/download-all", json={"documentIds": []}, headers=user["headers"]
    )
    assert r.status_code == 200


# ------------------------------------------------------------------ small cleanups


@pytest.mark.parametrize("bad", ["2026-W27-3", "20260701", "2026-7-1", "2026-07-01T00:00"])
async def test_date_param_must_be_exactly_yyyy_mm_dd(client: TestClient, bad: str) -> None:
    user = await make_user()
    r = client.get("/api/documents", params={"date": bad}, headers=user["headers"])
    assert r.status_code == 400


async def test_total_count_is_the_number_of_unique_ids(client: TestClient) -> None:
    user = await make_user()
    a = await make_document(user["_id"], invoiceNo="TC-1")
    r = client.post(
        "/api/documents/download-all",
        json={"documentIds": [a["id"], a["id"], "0" * 24]},
        headers=user["headers"],
    )
    h = r.headers
    assert (h["X-Total-Count"], h["X-Included-Count"], h["X-Skipped-Count"]) == ("2", "1", "1")
    row = await current_db().auditlogs.find_one({"action": "documents_download_all"})
    assert row is not None and row["context"]["requested"] == 2
