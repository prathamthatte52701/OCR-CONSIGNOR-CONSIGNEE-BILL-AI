"""Feature 20: GET /documents/training-stats = {trainedCount, correctedCount}.

trainedCount   = this user's documents with uploadStatus "processed".
correctedCount = this user's documents with edited == True (a saved correction).
Own documents only; permanently-flagged-deleted leftovers are never counted."""

from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.main import app
from testkit import make_document, make_user

URL = "/api/documents/training-stats"


@pytest.fixture(scope="module")
def client() -> Any:
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


async def doc(user: dict[str, Any], **fields: Any) -> None:
    await make_document(user["_id"], with_files=False, **fields)


def test_requires_a_login(client: TestClient) -> None:
    assert client.get(URL).status_code in (401, 403)


async def test_empty_account_gets_zeros(client: TestClient) -> None:
    user = await make_user()
    r = client.get(URL, headers=user["headers"])
    assert r.status_code == 200
    assert r.json() == {"trainedCount": 0, "correctedCount": 0}


async def test_definitions(client: TestClient) -> None:
    user = await make_user()
    await doc(user)  # processed, not edited
    await doc(user, edited=True)  # processed + corrected
    await doc(user, edited=False)
    await doc(user, uploadStatus="failed")  # not trained
    await doc(user, uploadStatus="processing")  # not trained
    await doc(user, uploadStatus="failed", edited=True)  # corrected only
    await doc(user, isDeleted=True)  # leftover flagged deleted: not counted
    r = client.get(URL, headers=user["headers"])
    assert r.json() == {"trainedCount": 3, "correctedCount": 2}


async def test_counts_only_the_callers_documents(client: TestClient) -> None:
    mine, other = await make_user(), await make_user()
    await doc(mine, edited=True)
    for _ in range(4):
        await doc(other, edited=True)
    assert client.get(URL, headers=mine["headers"]).json() == {
        "trainedCount": 1,
        "correctedCount": 1,
    }
    assert client.get(URL, headers=other["headers"]).json() == {
        "trainedCount": 4,
        "correctedCount": 4,
    }


async def test_response_has_only_the_two_numbers_no_text(client: TestClient) -> None:
    user = await make_user()
    await doc(user, edited=True, invoiceNo="SECRET-INV-1", consignee="SECRET CO")
    body = client.get(URL, headers=user["headers"]).json()
    assert set(body) == {"trainedCount", "correctedCount"}
    assert all(isinstance(v, int) for v in body.values())
    assert "SECRET" not in str(body)
