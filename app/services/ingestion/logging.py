"""Shared logging utilities for the ingestion pipeline."""
from __future__ import annotations

import logging
from pathlib import Path


_LOG_NAME = "app.ingestion"
_LOG_DIR = Path("data/logs")
_LOG_DIR.mkdir(parents=True, exist_ok=True)
_LOG_FILE = _LOG_DIR / "ingestion.log"

_IMPORTANT_EVENTS = {
    "STAGE_START",
    "STAGE_COMPLETE",
    "INGEST_START",
    "HANDLER_SELECTED",
    "NORMALIZATION_BEGIN",
    "NORMALIZATION_COMPLETE",
    "NORMALIZATION_REUSED",
    "VALIDATION_BEGIN",
    "VALIDATION_COMPLETE",
    "INGESTION_BEGIN",
    "INGESTION_COMPLETE",
    "INGESTION_ERROR",
    "DATABASE_WRITE_COMPLETE",
    "HANDLER_CONTEXT_RESOLVED",
    "PLATFORM_DIMENSION_ENSURED",
    "ACCOUNT_DIMENSION_ENSURED",
}


def get_ingestion_logger() -> logging.Logger:
    """Return a configured logger writing to the ingestion log file."""

    logger = logging.getLogger(_LOG_NAME)
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        handler = logging.FileHandler(_LOG_FILE, encoding="utf-8")
        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)s | %(message)s"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.propagate = False
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
