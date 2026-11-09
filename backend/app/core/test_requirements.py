"""requirements.txt hygiene: every runtime dependency is pinned exactly, none is listed twice,
dev tools stay in requirements-dev.txt, and the installed packages match the pins. The files
themselves are never changed by this test.

The installed-versions check is opt-in: run with CHECK_INSTALLED_PINS=1."""

import os
import re
from importlib.metadata import version
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
DEV_TOOLS = {"ruff", "black", "isort", "mypy", "pytest", "pytest-asyncio"}
PIN = re.compile(r"[A-Za-z0-9_.\-]+(\[[A-Za-z0-9,_\-]+\])?==\d[\w.]*")


def _lines(name: str) -> list[str]:
    out = []
    for raw in (ROOT / name).read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if line and not line.startswith("-"):
            out.append(line)
    return out


def _name(line: str) -> str:
    return re.split(r"[=<>\[ ]", line, maxsplit=1)[0].lower().replace("_", "-")


def test_every_runtime_requirement_is_pinned_to_an_exact_version() -> None:
    lines = _lines("requirements.txt")
    assert len(lines) >= 20
    for line in lines:
        assert PIN.fullmatch(line), f"not pinned with ==: {line}"


def test_no_package_is_listed_twice() -> None:
    names = [_name(line) for line in _lines("requirements.txt")]
    assert len(names) == len(set(names)), sorted(n for n in set(names) if names.count(n) > 1)
    dev = [_name(line) for line in _lines("requirements-dev.txt")]
    assert len(dev) == len(set(dev))


def test_dev_tools_live_only_in_the_dev_file() -> None:
    runtime = {_name(line) for line in _lines("requirements.txt")}
    assert not runtime & DEV_TOOLS
    dev_text = (ROOT / "requirements-dev.txt").read_text(encoding="utf-8")
    assert "-r requirements.txt" in dev_text
    assert DEV_TOOLS <= {_name(line) for line in _lines("requirements-dev.txt")}
    assert all("==" in line for line in _lines("requirements-dev.txt"))


def test_core_runtime_packages_are_present() -> None:
    runtime = {_name(line) for line in _lines("requirements.txt")}
    for pkg in ("fastapi", "motor", "pymongo", "pydantic", "pyjwt", "bcrypt", "groq", "paddleocr"):
        assert pkg in runtime, pkg
    assert "python-jose" not in runtime


@pytest.mark.skipif(
    os.environ.get("CHECK_INSTALLED_PINS") != "1",
    reason="opt-in: set CHECK_INSTALLED_PINS=1 to compare installed packages with the pins",
)
def test_installed_versions_match_the_pins() -> None:
    for line in _lines("requirements.txt"):
        name, pinned = re.sub(r"\[.*\]", "", line).split("==")
        if name.lower().startswith("opencv"):
            continue  # the dev venv may carry another build of the same release
        assert version(name) == pinned, f"{name}: installed {version(name)} != pinned {pinned}"
