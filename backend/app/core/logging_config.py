"""Structured logging via loguru, routing stdlib `logging` (uvicorn, ocr/preprocessing.py)
through the same sink so every log line - app and framework - shares one format/level."""

import logging
import sys

from loguru import logger

from app.core.config import settings


class _InterceptHandler(logging.Handler):
    """Standard loguru recipe for capturing stdlib `logging` records into loguru's sinks."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            level: str | int = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        frame, depth = logging.currentframe(), 2
        while frame.f_back and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


def configure_logging() -> None:
    """Call once at process startup, before the app starts serving requests."""
    level = "INFO" if settings.is_production else "DEBUG"

    logger.remove()
    logger.add(
        sys.stderr,
        level=level,
        colorize=not settings.is_production,
        backtrace=not settings.is_production,
        # diagnose prints local variable values in tracebacks - handy in dev, but a stray
        # password/token could be in scope during an auth exception, so it stays off in prod.
        diagnose=not settings.is_production,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
        ),
    )

    logging.basicConfig(handlers=[_InterceptHandler()], level=0, force=True)
    for noisy_logger in ("uvicorn", "uvicorn.access", "uvicorn.error"):
        logging.getLogger(noisy_logger).handlers = []
        logging.getLogger(noisy_logger).propagate = True

    # pymongo's DEBUG level logs every connection checkout/command (driver plumbing, not app
    # logic) - drown out nothing else at DEBUG in dev by keeping this one driver quiet.
    logging.getLogger("pymongo").setLevel(logging.WARNING)
