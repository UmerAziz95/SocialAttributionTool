"""Pydantic models used by the ingestion API."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class FileUploadResponse(BaseModel):
    saved_path: Path = Field(..., description="Absolute path to the stored file")
    size_bytes: int = Field(..., ge=0)


class FileIngestionRequest(BaseModel):
    file_path: Path = Field(..., description="Path to the uploaded file")
    column_map: dict[str, Any] | None = Field(default=None, description="Dimension or field overrides")
    currency_code: str | None = Field(default=None, description="Currency code override")
    attribution: str | None = Field(default=None, description="Attribution window override")
    dry_run: bool = False
    fail_fast: bool = False
    batch_size: int | None = Field(default=None, ge=1, description="Optional batch size for DB writes")


class FileIngestionResponse(BaseModel):
    inserted: int
    updated: int
    skipped: int
    warnings: list[str]
    duration_sec: float
    normalized_path: Path
