"""Typed helpers used across ingestion services."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class IngestionContext:
    file_path: Path
    normalized_path: Path
    column_map: dict[str, Any] = field(default_factory=dict)
    currency_code: str | None = None
    attribution: str | None = None
    dry_run: bool = False
    fail_fast: bool = False
    batch_size: int = 500


@dataclass(slots=True)
class IngestionResult:
    inserted: int = 0
    updated: int = 0
    skipped: int = 0
    warnings: list[str] = field(default_factory=list)
    status: str = "pending"
    summary: str = ""
    started_at: datetime = field(default_factory=datetime.utcnow)
    finished_at: datetime | None = None

    @property
    def duration_seconds(self) -> float:
        if not self.finished_at:
            return 0.0
        return (self.finished_at - self.started_at).total_seconds()
