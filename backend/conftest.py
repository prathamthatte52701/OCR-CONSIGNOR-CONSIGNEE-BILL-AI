"""Test-run safety harness. Loaded by pytest before any test module (and so before the app) is
imported.

Guarantees:
  1. The real database is never reachable from a test run. MONGO_DB_NAME is forced to a name
     ending in "_test" and the run ABORTS if it somehow does not; MONGO_URI is replaced so even a
     leaked real client could not reach Atlas.
  2. By default an in-process fake Mongo (fake_mongo.py) replaces Motor / PyMongo / GridFS.
  3. To run against a real server instead, set TEST_MONGO_URI (a local mongod - NOT Atlas prod).
     The "_test" database name rule still applies and the test database is dropped at the end.
"""

import os
from collections.abc import Iterator
from typing import Any

import pytest

_TEST_DB_NAME = os.environ.get("TEST_MONGO_DB_NAME", "docintel_cons_cons_test")
_REAL_TEST_URI = os.environ.get("TEST_MONGO_URI")
_FAKE_URI = "mongodb://fake-test-host.invalid:27017/" + _TEST_DB_NAME

# --- must happen before `app` is imported anywhere ---------------------------------------
os.environ["MONGO_DB_NAME"] = _TEST_DB_NAME
# Startup recovery re-queues stuck documents (real OCR). Tests that exercise it turn it on
# themselves; everything else must never trigger it.
os.environ["RECOVER_INTERRUPTED_UPLOADS"] = "false"
# The API docs are off by default; a test (not the environment) decides when to look at them.
os.environ["ENABLE_DOCS"] = "false"
os.environ["MONGO_URI"] = _REAL_TEST_URI or _FAKE_URI

if not os.environ["MONGO_DB_NAME"].endswith("_test"):
    raise pytest.UsageError(
        f"Refusing to run tests: MONGO_DB_NAME={os.environ['MONGO_DB_NAME']!r} does not end in "
        "'_test'."
    )

USING_FAKE_MONGO = _REAL_TEST_URI is None

if USING_FAKE_MONGO:
    import gridfs  # noqa: F401  (imported so motor's lazy deps are loaded before patching)
    import motor.motor_asyncio as _motor
    import pymongo

    import fake_mongo

    _motor.AsyncIOMotorClient = fake_mongo.FakeAsyncMongoClient  # type: ignore[misc,assignment]
    _motor.AsyncIOMotorGridFSBucket = fake_mongo.FakeGridFSBucket  # type: ignore[misc,assignment]
    pymongo.MongoClient = fake_mongo.FakeSyncMongoClient  # type: ignore[misc,assignment]


_real_client: Any = None


def _real_test_db() -> Any:
    """Sync handle on the real *_test database (only ever used when TEST_MONGO_URI is set)."""
    global _real_client
    from pymongo import MongoClient

    assert os.environ["MONGO_DB_NAME"].endswith("_test")  # never touch a non-test database
    if _real_client is None:
        _real_client = MongoClient(os.environ["MONGO_URI"], tz_aware=True)
    return _real_client[os.environ["MONGO_DB_NAME"]]


@pytest.fixture(autouse=True)
def _isolated_state() -> Iterator[None]:
    """Fresh data and fresh rate-limit counters for every test (indexes are kept)."""
    from app.core import rate_limit

    if USING_FAKE_MONGO:
        fake_mongo.STORE.clear_data()
    else:
        db = _real_test_db()
        for name in db.list_collection_names():
            if not name.startswith("system."):
                db[name].delete_many({})
    rate_limit.limiter.reset()
    rate_limit._email_storage.reset()
    yield


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """Drop the test database when a real server was used (the fake vanishes with the process)."""
    if USING_FAKE_MONGO:
        return
    db = _real_test_db()
    assert db.name.endswith("_test")
    _real_client.drop_database(db.name)
    _real_client.close()
