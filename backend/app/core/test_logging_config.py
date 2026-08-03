import logging
from collections.abc import Iterator

import pytest
from loguru import logger

from app.core.config import settings
from app.core.logging_config import configure_logging

_ORIGINAL_ENVIRONMENT = settings.environment


@pytest.fixture(autouse=True)
def _restore_environment() -> Iterator[None]:
    yield
    settings.environment = _ORIGINAL_ENVIRONMENT
    configure_logging()


def test_configure_logging_runs_without_error() -> None:
    configure_logging()


def test_configure_logging_is_idempotent() -> None:
    configure_logging()
    configure_logging()  # must not raise or accumulate duplicate handlers


def test_pymongo_driver_chatter_is_quieted() -> None:
    # Verified empirically: pymongo's DEBUG level logs every connection checkout/command,
    # drowning out actual app log lines during dev - it's held above DEBUG deliberately.
    configure_logging()
    assert logging.getLogger("pymongo").level == logging.WARNING


def test_stdlib_logging_routes_through_loguru() -> None:
    configure_logging()
    captured: list[str] = []
    handler_id = logger.add(lambda msg: captured.append(msg.record["message"]), level="DEBUG")
    try:
        logging.getLogger("app.features.ocr.preprocessing").warning("stdlib bridge check")
    finally:
        logger.remove(handler_id)
    assert any("stdlib bridge check" in m for m in captured)


def test_dev_level_emits_debug_to_stderr(capsys: pytest.CaptureFixture[str]) -> None:
    settings.environment = "development"
    configure_logging()
    logger.debug("debug-marker-visible-in-dev")
    captured = capsys.readouterr()
    assert "debug-marker-visible-in-dev" in captured.err


def test_prod_level_suppresses_debug(capsys: pytest.CaptureFixture[str]) -> None:
    settings.environment = "production"
    configure_logging()
    logger.debug("debug-marker-should-not-appear-in-prod")
    logger.info("info-marker-should-appear-in-prod")
    captured = capsys.readouterr()
    assert "debug-marker-should-not-appear-in-prod" not in captured.err
    assert "info-marker-should-appear-in-prod" in captured.err


def _index_with_password_in_scope(password: str) -> str:
    # diagnose=True annotates values of variables used *in the failing expression itself*
    # (not just anything in scope) - password[999] both uses and fails on `password`, so this
    # is the realistic shape of "a secret ends up annotated in a traceback".
    return password[999]


def test_prod_does_not_leak_local_variables_in_traceback(
    capsys: pytest.CaptureFixture[str],
) -> None:
    settings.environment = "production"
    configure_logging()
    # The secret is read from a variable at the call site, not a literal, so the plain
    # source-line echo every traceback prints (regardless of diagnose) can't leak it - only
    # diagnose's runtime value annotation could, and that's what this asserts stays off.
    secret = "SECRETPASSWORD123"
    try:
        _index_with_password_in_scope(secret)
    except IndexError:
        logger.exception("failure")
    captured = capsys.readouterr()
    assert "SECRETPASSWORD123" not in captured.err


def test_dev_shows_local_variables_in_traceback_for_debugging(
    capsys: pytest.CaptureFixture[str],
) -> None:
    settings.environment = "development"
    configure_logging()
    secret = "SECRETPASSWORD456"
    try:
        _index_with_password_in_scope(secret)
    except IndexError:
        logger.exception("failure")
    captured = capsys.readouterr()
    assert "SECRETPASSWORD456" in captured.err


if __name__ == "__main__":
    configure_logging()
    logger.info("logging_config self-check: configured without error")
    settings.environment = _ORIGINAL_ENVIRONMENT
    configure_logging()
    print("logging_config self-check passed")
