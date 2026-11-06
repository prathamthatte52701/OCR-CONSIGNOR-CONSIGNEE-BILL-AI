"""Feature 8: stats (needsReview/processing/corrected), status filter, /storage."""

from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.main import app
from testkit import make_document, make_user

URL = "/api/documents"


@pytest.fixture(scope="module")
def client() -> Any:
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


async def doc(user: dict[str, Any], **fields: Any) -> str:
    return str((await make_document(user["_id"], with_files=False, **fields))["id"])


def get(client: TestClient, user: dict[str, Any], path: str, **params: Any) -> Any:
    r = client.get(f"{URL}{path}", params=params, headers=user["headers"])
    assert r.status_code == 200, r.text
    return r.json()


async def test_stats_needs_review_matches_list_total(client: TestClient) -> None:
    user = await make_user()
    await doc(user, uploadStatus="failed")
    await doc(user, hasLowConfidenceFields=True)
    await doc(user, hasReviewWarnings=True)
    await doc(user, hasReviewWarnings=False, hasLowConfidenceFields=False)
    await doc(user)  # legacy, no flags
    stats = get(client, user, "/stats")
    assert stats["needsReview"] == 3
    assert stats["needsReview"] == get(client, user, "", needsReview="true")["total"]


async def test_processing_and_corrected_counts_skip_others_and_deleted(
    client: TestClient,
) -> None:
    user, other = await make_user(), await make_user()
    await doc(user, uploadStatus="uploaded")
    await doc(user, uploadStatus="processing")
    await doc(user, edited=True)
    await doc(user, edited=False)
    await doc(user, uploadStatus="processing", isDeleted=True)
    await doc(user, edited=True, isDeleted=True)
    await doc(other, uploadStatus="processing", edited=True)
    stats = get(client, user, "/stats")
    assert (stats["processing"], stats["corrected"]) == (2, 1)
    assert stats["total"] == 4  # old fields unchanged: deleted + other user excluded


async def test_status_filter(client: TestClient) -> None:
    user = await make_user()
    bad = await doc(user, uploadStatus="failed", invoiceNo="AB-1", hasLowConfidenceFields=True)
    await doc(user, uploadStatus="failed", invoiceNo="ZZ-2")
    good = await doc(user, uploadStatus="processed", invoiceNo="AB-3", hasReviewWarnings=True)
    await doc(user, uploadStatus="processed", invoiceNo="ZZ-4")

    def ids(**params: Any) -> set[str]:
        return {i["id"] for i in get(client, user, "", **params)["items"]}

    assert len(ids(status="failed")) == 2
    assert len(ids(status="processed")) == 2
    assert ids(status="failed", search="ab-") == {bad}
    assert ids(status="processed", needsReview="true") == {good}
    r = client.get(URL, params={"status": "bogus"}, headers=user["headers"])
    assert r.status_code == 422


async def test_list_rows_expose_has_review_warnings(client: TestClient) -> None:
    user = await make_user()
    await doc(user)  # legacy
    await doc(user, hasReviewWarnings=True)
    flags = sorted(i["hasReviewWarnings"] for i in get(client, user, "")["items"])
    assert flags == [False, True]


async def test_storage_counts_only_kept_parts(client: TestClient) -> None:
    user, other = await make_user(), await make_user()
    await doc(user, part1Size=100, part2Size=50)  # both kept: 150
    await doc(user, part1Size=100, part2Size=50, part1FilePurged=True)  # only part2: 50
    await doc(user, part1Size=100, part2Size=50, part1FilePurged=True, part2FilePurged=True)
    await doc(user, part1Size=10)  # missing part2 size counts 0
    await doc(user, part1Size=999, part2Size=999, isDeleted=True)
    await doc(other, part1Size=999, part2Size=999)
    assert get(client, user, "/storage") == {"documents": 3, "bytes": 210}


async def test_storage_empty_user(client: TestClient) -> None:
    user = await make_user()
    assert get(client, user, "/storage") == {"documents": 0, "bytes": 0}


@pytest.mark.parametrize("path", ["/stats", "/storage"])
def test_requires_token(client: TestClient, path: str) -> None:
    assert client.get(f"{URL}{path}").status_code == 401
