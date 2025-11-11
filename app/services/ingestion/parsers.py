"""Parsing helpers used by ingestion handlers."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Iterable


DATE_FORMATS: Iterable[str] = (
    "%Y-%m-%d",
    "%m/%d/%Y",
    "%d/%m/%Y",
    "%Y/%m/%d",
)


def parse_date(value: str) -> date | None:
    value = (value or "").strip()
    if not value:
        return None

    if "-" in value and " " in value:
        # Handle ranges such as "October 13, 2025 - October 19, 2025"
        parts = [part.strip() for part in value.split("-") if part.strip()]
        if parts:
            return parse_date(parts[0])
        return None

    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue

    try:
        return datetime.fromisoformat(value).date()
    except ValueError:
        return None


def parse_int(value: str) -> int | None:
    value = (value or "").strip()
    if not value:
        return None
    try:
        return int(float(value.replace(",", "")))
    except (ValueError, TypeError):
        return None


def parse_decimal(value: str) -> Decimal | None:
    value = (value or "").strip()
    if not value:
        return None
    cleaned = value.replace(",", "")
    try:
        return Decimal(cleaned)
    except (InvalidOperation, ValueError):
        return None
