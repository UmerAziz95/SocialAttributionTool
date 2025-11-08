"""Shared logging utilities for the ingestion pipeline."""
from __future__ import annotations

import logging
from pathlib import Path


_LOG_NAME = "app.ingestion"
_LOG_DIR = Path("data/logs")
_LOG_DIR.mkdir(parents=True, exist_ok=True)
_LOG_FILE = _LOG_DIR / "ingestion.log"


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


def log_event(event: str, **fields: object) -> None:
    """Log a structured ingestion event in a consistent key=value format."""

    logger = get_ingestion_logger()
    serialized_fields = " | ".join(
        f"{key}={value}" for key, value in sorted(fields.items())
    )
    if serialized_fields:
        message = f"{event} | {serialized_fields}"
    else:
        message = event
    logger.info(message)


__all__ = ["get_ingestion_logger", "log_event"]
