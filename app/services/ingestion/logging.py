"""Shared logging utilities for the ingestion pipeline."""
from __future__ import annotations

import logging
import os
from pathlib import Path

from app.core.config import PROJECT_ROOT


_LOG_NAME = "app.ingestion"
# Anchor the log directory to the repository root so the file is always
# written to a predictable location regardless of the process working
# directory (for example when running uvicorn from a different folder).
_LOG_DIR = (PROJECT_ROOT / "data" / "logs").resolve()
_LOG_DIR.mkdir(parents=True, exist_ok=True)
_LOG_FILE = _LOG_DIR / "ingestion.log"
_LOG_FILE.touch(exist_ok=True)

_IMPORTANT_EVENTS = {
    "INGEST_START",
    "HANDLER_SELECTED",
    "NORMALIZATION_COMPLETE",
    "NORMALIZATION_REUSED",
    "VALIDATION_COMPLETE",
    "INGESTION_BEGIN",
    "INGESTION_COMPLETE",
    "INGESTION_ERROR",
    "DATABASE_WRITE_COMPLETE",
    "HANDLER_CONTEXT_RESOLVED",
    "PLATFORM_DIMENSION_ENSURED",
    "ACCOUNT_DIMENSION_ENSURED",
    "INGESTION_FILE_SUMMARY",
    "MARKETING_FACT_SUMMARY",
    "MARKETING_NO_ROWS",
}


def get_ingestion_logger() -> logging.Logger:
    """Return a configured logger writing to the ingestion log file."""

    logger = logging.getLogger(_LOG_NAME)
    if not logger.handlers:
        configured_level = os.getenv("INGESTION_LOG_LEVEL", "DEBUG").upper()
        log_level = getattr(logging, configured_level, logging.DEBUG)

        logger.setLevel(log_level)
        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)s | %(message)s"
        )

        file_handler = logging.FileHandler(_LOG_FILE, encoding="utf-8")
        file_handler.setLevel(log_level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

        stream_handler = logging.StreamHandler()
        stream_handler.setLevel(log_level)
        stream_handler.setFormatter(formatter)
        logger.addHandler(stream_handler)
        logger.propagate = False

        logger.debug("Initialized ingestion logger", extra={"level": log_level})
    return logger


def log_event(event: str, *, level: int | None = None, **fields: object) -> None:
    """Log a structured ingestion event in a consistent key=value format.

    Parameters
    ----------
    event:
        Short identifier describing the event (e.g. ``"NORMALIZATION_BEGIN"``).
    level:
        Optional logging level to use, defaults to :data:`logging.INFO`.
    **fields:
        Additional key/value attributes serialized alongside the event name.
    """

    logger = get_ingestion_logger()
    if level is None:
        level = logging.INFO if event in _IMPORTANT_EVENTS else logging.DEBUG
    if not logger.isEnabledFor(level):
        return
    serialized_fields = " | ".join(
        f"{key}={value}" for key, value in sorted(fields.items())
    )
    message = event
    if serialized_fields:
        message = f"{message} | {serialized_fields}"
    logger.log(level, message)


def get_ingestion_log_path() -> Path:
    """Expose the ingestion log destination so API responses can surface it."""

    return _LOG_FILE


__all__ = ["get_ingestion_logger", "get_ingestion_log_path", "log_event"]
