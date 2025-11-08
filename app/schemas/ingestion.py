"""Pydantic models used by the ingestion API."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class FileUploadResponse(BaseModel):
    """Response returned after a successful file upload."""

    saved_path: Path = Field(..., description="Absolute path to the stored file")
    size_bytes: int = Field(..., ge=0, description="Total bytes persisted to disk")

    model_config = {
        "json_schema_extra": {
            "example": {
                "saved_path": "/app/data/uploads/DMA_Performance_Meta.csv",
                "size_bytes": 12038,
            }
        }
    }


class FileIngestionRequest(BaseModel):
    """Payload describing how to ingest a stored marketing file."""

    file_path: Path = Field(..., description="Path to the uploaded file")
    column_map: dict[str, Any] | None = Field(
        default=None,
        description="Dimension or field overrides",
        examples=[{"platform_id": 1, "account_id": 10}],
    )
    currency_code: str | None = Field(
        default=None,
        description="Currency code override",
        examples=["AUD"],
    )
    attribution: str | None = Field(
        default=None,
        description="Attribution window override",
        examples=["Incremental"],
    )
    dry_run: bool = Field(
        default=False,
        description="If true, run validation without writing to the database",
    )
    fail_fast: bool = Field(
        default=False,
        description="If true, abort on the first validation error",
    )
    batch_size: int | None = Field(
        default=None,
        ge=1,
        description="Optional batch size for DB writes",
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "file_path": "/app/data/uploads/DMA_Performance_Meta.csv",
                "column_map": {"platform_id": 1, "account_id": 10},
                "currency_code": "AUD",
                "attribution": "Incremental",
                "dry_run": False,
                "fail_fast": False,
                "batch_size": 500,
            }
        }
    }


class FileIngestionResponse(BaseModel):
    """Outcome from a handler run."""

    inserted: int = Field(..., ge=0, description="Number of new records written")
    updated: int = Field(..., ge=0, description="Number of existing rows updated")
    skipped: int = Field(..., ge=0, description="Rows skipped after validation errors")
    warnings: list[str] = Field(default_factory=list, description="Non-fatal warnings")
    status: str = Field(..., description="Overall ingestion status (ingested, dry_run, no_data, failed)")
    summary: str = Field(..., description="Human-readable description of what happened during ingestion")
    duration_sec: float = Field(..., ge=0, description="Total execution time in seconds")
    normalized_path: Path = Field(..., description="Location of the normalized CSV copy")

    model_config = {
        "json_schema_extra": {
            "example": {
                "inserted": 250,
                "updated": 12,
                "skipped": 3,
                "warnings": [
                    "Row 4: unknown DMA 'Reels & Feeds | US Only' — add a column_map.dma_map entry"
                ],
                "status": "ingested",
                "summary": "Inserted records into the warehouse. Inserted=250, Updated=12, Skipped=3.",
                "duration_sec": 4.21,
                "normalized_path": "/app/data/uploads/DMA_Performance_Meta__normalized.csv",
            }
        }
    }
