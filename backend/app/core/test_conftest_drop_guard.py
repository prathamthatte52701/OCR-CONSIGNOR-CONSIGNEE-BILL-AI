"""The test-run guard in conftest.py: a run on a database name that does not end in `_test` is
refused, and the live run is on a `_test` name. Checked in a subprocess, so nothing here can
touch the current process's settings or any database."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from app.core.config import settings

BACKEND = Path(__file__).resolve().parents[2]


def _import_conftest(db_name: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "TEST_MONGO_DB_NAME": db_name, "PYTHONPATH": str(BACKEND)}
    env.pop("TEST_MONGO_URI", None)  # always the in-process fake, never a real server
    return subprocess.run(
        [sys.executable, "-c", "import conftest"],
        cwd=BACKEND, env=env, capture_output=True, text=True, timeout=120,
    )  # fmt: skip


@pytest.mark.parametrize("name", ["docintel_cons_cons", "admin", "prod", "x_test_backup", ""])
def test_a_non_test_database_name_aborts_the_run(name: str) -> None:
    out = _import_conftest(name)
    assert out.returncode != 0
    assert "Refusing to run tests" in out.stderr


def test_a_test_database_name_is_accepted() -> None:
    out = _import_conftest("docintel_cons_cons_test")
    assert out.returncode == 0, out.stderr[-400:]


def test_this_run_uses_a_test_database_and_the_fake_uri() -> None:
    assert settings.mongo_db_name.endswith("_test")
    assert os.environ["MONGO_DB_NAME"].endswith("_test")
    assert (
        settings.mongo_uri != ""
        and ".invalid" in settings.mongo_uri
        or os.environ.get("TEST_MONGO_URI")
    )


def test_the_session_hooks_force_safe_flags() -> None:
    assert os.environ["ENABLE_DOCS"] == "false"
    assert os.environ["RECOVER_INTERRUPTED_UPLOADS"] == "false"
