"""Fixtures for the chat tests (ported from ACKN): `db`, async `client`, `make_user`, `trio`."""

from collections.abc import AsyncIterator
from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

import testkit
from app.core.config import settings
from app.core.database import close_mongo_connection, connect_to_mongo, get_database
from app.main import app


@pytest_asyncio.fixture
async def db() -> AsyncIterator[Any]:
    assert settings.mongo_db_name.endswith("_test")  # the same guard conftest.py enforces
    await connect_to_mongo()
    try:
        yield get_database()
    finally:
        await close_mongo_connection()


@pytest_asyncio.fixture
async def client(db: Any) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


class Account:
    def __init__(self, doc: dict[str, Any]) -> None:
        self.id = doc["_id"]
        self.email = doc["email"]
        self.username = doc["username"]
        self.password = testkit.PASSWORD
        self.headers: dict[str, str] = doc["headers"]


@pytest.fixture
def new_password() -> str:
    return testkit.PASSWORD


@pytest_asyncio.fixture
async def make_user(db: Any) -> Any:
    async def _make(
        role: str = "user", status: str | None = "approved", username: str | None = None
    ) -> Account:
        return Account(await testkit.make_user(role=role, status=status, username=username))

    return _make


@pytest.fixture
async def trio(make_user: Any) -> tuple[Any, Any, Any]:
    """(user, admin, second admin). `_admin` picks the upload recipient field (userId/toAdminId)."""
    u = await make_user()
    adm, adm2 = await make_user(role="admin"), await make_user(role="admin")
    adm._admin = adm2._admin = True
    return u, adm, adm2
