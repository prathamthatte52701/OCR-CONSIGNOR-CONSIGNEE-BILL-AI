"""Edit guards of apply_field_correction (shared by the user and admin routes): an empty value is
refused except for irnNo, and the final write only lands while the document is still finished."""

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.features.documents.correction_service import apply_field_correction
from app.main import app
from testkit import current_db, make_document, make_user

ITEM = {"srNo": "1", "description": "Bolt", "hsnSac": "7318", "quantity": "2"}


@pytest.fixture(scope="module")
def client() -> Iterator[TestClient]:
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


def patch(client: TestClient, user: dict[str, Any], doc_id: str, field: str, value: Any) -> Any:
    return client.patch(
        f"/api/documents/{doc_id}/correct",
        json={"field": field, "value": value},
        headers=user["headers"],
    )


@pytest.mark.parametrize("value", [None, "", "   ", "\t \n"])
@pytest.mark.parametrize("field", ["reason", "lineItems.0.description"])
async def test_empty_or_spaces_value_is_refused(client: TestClient, field: str, value: Any) -> None:
    user = await make_user()
    doc = await make_document(user["_id"], reason="old", lineItems=[dict(ITEM)])
    r = patch(client, user, doc["id"], field, value)
    assert r.status_code == 400 and r.json()["detail"] == "Please enter a value before saving."
    assert await current_db().corrections.count_documents({}) == 0
    assert (await current_db().documents.find_one({"_id": doc["_id"]}))["reason"] == "old"


@pytest.mark.parametrize("value", [None, "", "  "])
async def test_irn_empty_clears_the_field(client: TestClient, value: Any) -> None:
    user = await make_user()
    doc = await make_document(user["_id"], irnNo="ABC123")
    assert patch(client, user, doc["id"], "irnNo", value).status_code == 200
    saved = await current_db().documents.find_one({"_id": doc["_id"]})
    assert saved["irnNo"] in (None, "")


async def test_normal_value_is_trimmed_and_saved(client: TestClient) -> None:
    user = await make_user()
    doc = await make_document(user["_id"], reason="old", lineItems=[dict(ITEM)])
    assert patch(client, user, doc["id"], "reason", "  new reason  ").status_code == 200
    assert patch(client, user, doc["id"], "lineItems.0.description", "Nut").status_code == 200
    saved = await current_db().documents.find_one({"_id": doc["_id"]})
    assert saved["reason"] == "new reason" and saved["lineItems"][0]["description"] == "Nut"
    assert saved["edited"] is True and saved["reasonConfidence"] == 100
    assert await current_db().corrections.count_documents({}) == 2


async def test_edit_while_processing_is_409(client: TestClient) -> None:
    user = await make_user()
    doc = await make_document(user["_id"], uploadStatus="processing")
    r = patch(client, user, doc["id"], "reason", "x")
    assert r.status_code == 409
    assert r.json()["detail"] == "Cannot edit while the document is still processing."


async def test_status_changing_between_read_and_write_is_409_and_writes_nothing() -> None:
    user = await make_user()
    db = current_db()
    doc = await make_document(user["_id"], reason="old")
    stale = await db.documents.find_one({"_id": doc["_id"]})  # read says "processed"
    await db.documents.update_one({"_id": doc["_id"]}, {"$set": {"uploadStatus": "processing"}})
    with pytest.raises(HTTPException) as exc:
        await apply_field_correction(
            db, stale, "reason", "new", actor_user_id=user["_id"], by_admin=False
        )
    assert exc.value.status_code == 409
    assert (await db.documents.find_one({"_id": doc["_id"]}))["reason"] == "old"
    assert await db.corrections.count_documents({}) == 0
    assert await db.auditlogs.count_documents({"action": "document_corrected"}) == 0


async def test_admin_route_follows_the_same_rules(client: TestClient) -> None:
    admin, owner = await make_user(role="admin"), await make_user()
    doc = await make_document(owner["_id"], reason="old")
    url = f"/api/admin/documents/{doc['id']}"
    empty = client.patch(url, json={"field": "reason", "value": " "}, headers=admin["headers"])
    assert empty.status_code == 400
    ok = client.patch(url, json={"field": "reason", "value": "fixed"}, headers=admin["headers"])
    assert ok.status_code == 200
    busy = await make_document(owner["_id"], uploadStatus="processing")
    r = client.patch(
        f"/api/admin/documents/{busy['id']}",
        json={"field": "reason", "value": "x"},
        headers=admin["headers"],
    )
    assert r.status_code == 409
