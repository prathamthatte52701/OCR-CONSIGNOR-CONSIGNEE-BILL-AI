"""Offline unit tests for the admin-approval gate (no database needed)."""

import pytest
from fastapi import HTTPException

from app.features.admin.router import _status_query
from app.features.auth.dependencies import raise_if_not_approved

PENDING = "Waiting for admin approval."
REJECTED = "Your request was not approved. Contact the admin."


def test_raise_if_not_approved_messages() -> None:
    raise_if_not_approved({"status": "approved"})  # no exception
    raise_if_not_approved({})  # legacy account, no status field
    with pytest.raises(HTTPException) as pending:
        raise_if_not_approved({"status": "pending"})
    assert pending.value.status_code == 403 and pending.value.detail["message"] == PENDING
    with pytest.raises(HTTPException) as rejected:
        raise_if_not_approved({"status": "rejected"})
    assert rejected.value.status_code == 403 and rejected.value.detail["message"] == REJECTED
    with pytest.raises(HTTPException):
        raise_if_not_approved({"status": "anything-unknown"})  # fail closed on unknown values


def test_status_query_treats_missing_status_as_approved() -> None:
    assert _status_query("approved") == {
        "$or": [{"status": "approved"}, {"status": {"$exists": False}}]
    }
    assert _status_query("pending") == {"status": "pending"}
    assert _status_query("rejected") == {"status": "rejected"}
