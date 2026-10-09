"""T14: /docs, /redoc and /openapi.json are off unless ENABLE_DOCS=true - in EVERY environment
(they used to be on whenever NODE_ENV was not "production")."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app

BACKEND = Path(__file__).resolve().parents[2]
DOC_PATHS = ("/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect")


@pytest.fixture(scope="module")
def client() -> TestClient:
    with TestClient(app, raise_server_exceptions=False) as c:
        return c


@pytest.mark.parametrize("path", DOC_PATHS)
def test_docs_endpoints_are_404_by_default(client: TestClient, path: str) -> None:
    assert client.get(path).status_code == 404


def test_the_app_is_built_without_any_docs_urls_by_default() -> None:
    assert app.docs_url is None and app.redoc_url is None and app.openapi_url is None


def test_api_routes_still_work_with_docs_off(client: TestClient) -> None:
    assert client.get("/health").status_code == 200


def _app_docs_urls(env_overrides: dict[str, str]) -> dict[str, object]:
    """Imports the app in a fresh interpreter with the given environment; returns its docs URLs."""
    code = (
        "import json, sys; sys.path.insert(0, '.'); import conftest; from app.main import app; "
        "print(json.dumps([app.docs_url, app.redoc_url, app.openapi_url]))"
    )
    env = {**os.environ, **env_overrides}
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=BACKEND,
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert result.returncode == 0, result.stderr[-800:]
    docs, redoc, openapi = json.loads(result.stdout.strip().splitlines()[-1])
    return {"docs": docs, "redoc": redoc, "openapi": openapi}


@pytest.mark.parametrize("environment", ["development"])
def test_docs_stay_off_in_development_unless_flagged(environment: str) -> None:
    # conftest (imported in the child) forces ENABLE_DOCS=false, so NODE_ENV alone can't turn it on
    urls = _app_docs_urls({"NODE_ENV": environment})
    assert urls == {"docs": None, "redoc": None, "openapi": None}


def test_enable_docs_true_turns_them_on() -> None:
    # Imports app.main directly (no conftest) so ENABLE_DOCS=true is honoured. Settings come from
    # the environment; the dummy Mongo URI guarantees nothing real can be reached from this child.
    code = (
        "import json, os; os.environ['MONGO_URI']='mongodb://fake-test-host.invalid:27017/x_test'; "
        "os.environ['MONGO_DB_NAME']='x_test'; from app.main import app; "
        "print(json.dumps([app.docs_url, app.redoc_url, app.openapi_url]))"
    )
    env = {**os.environ, "ENABLE_DOCS": "true"}
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=BACKEND,
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert result.returncode == 0, result.stderr[-800:]
    assert json.loads(result.stdout.strip().splitlines()[-1]) == [
        "/docs",
        "/redoc",
        "/openapi.json",
    ]


@pytest.mark.parametrize("value", ["0"])
def test_falsey_values_keep_docs_off(value: str) -> None:
    code = (
        "import json, os; os.environ['MONGO_URI']='mongodb://fake-test-host.invalid:27017/x_test'; "
        "os.environ['MONGO_DB_NAME']='x_test'; from app.main import app; "
        "print(json.dumps([app.docs_url, app.redoc_url, app.openapi_url]))"
    )
    env = {**os.environ, "ENABLE_DOCS": value}
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=BACKEND,
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )
    if value == "":
        assert result.returncode != 0 or json.loads(result.stdout.strip().splitlines()[-1]) == [
            None,
            None,
            None,
        ]
    else:
        assert result.returncode == 0, result.stderr[-800:]
        assert json.loads(result.stdout.strip().splitlines()[-1]) == [None, None, None]
