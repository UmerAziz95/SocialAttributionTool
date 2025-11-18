"""Pydantic models used by the ingestion API."""
from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class IngestionPlatform(str, Enum):
    """Supported marketing platforms for grouped uploads."""

    TIKTOK = "tiktok"
    SHOPIFY = "shopify"
    META = "meta"
    PINTEREST = "pinterest"
    GOOGLE = "google"


class UploadedFileMetadata(BaseModel):
    """Metadata captured for each uploaded file."""

    filename: str = Field(..., description="Original filename supplied by the client")
    saved_path: Path = Field(..., description="Absolute path to the stored file")
    size_bytes: int = Field(..., ge=0, description="Total bytes persisted to disk")

    model_config = {
        "json_schema_extra": {
            "example": {
                "filename": "DMA_Performance_Meta.csv",
                "saved_path": "/app/data/uploads/meta/DMA_Performance_Meta.csv",
                "size_bytes": 12038,
            }
        }
    }


class MultiFileUploadResponse(BaseModel):
    """Response returned after uploading one or more files for a platform."""

    platform: IngestionPlatform = Field(..., description="Platform folder the files were stored under")
    files: List[UploadedFileMetadata] = Field(
        ..., description="Metadata for each uploaded file in the request"
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "platform": "tiktok",
                "files": [
                    {
                        "filename": "tiktok_by_dma.csv",
                        "saved_path": "/app/data/uploads/tiktok/tiktok_by_dma.csv",
                        "size_bytes": 2314,
                    },
                    {
                        "filename": "tiktok_by_region.csv",
                        "saved_path": "/app/data/uploads/tiktok/tiktok_by_region.csv",
                        "size_bytes": 5428,
                    },
                ],
            }
        }
    }


class FileIngestionRequest(BaseModel):
    """Payload describing how to ingest files stored for a platform."""

    platform: IngestionPlatform = Field(
        ..., description="Platform folder whose files should be ingested"
    )
    filenames: Optional[List[str]] = Field(
        default=None,
        description=(
            "Optional subset of filenames to ingest. When omitted, every file in "
            "the platform's upload directory is processed."
        ),
        examples=[["DMA_Performance_Meta.csv", "Region_Performance_Meta.csv"]],
    )
    column_map: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Dimension or field overrides",
        examples=[{"platform_id": 1, "account_id": 10}],
    )
    currency_code: Optional[str] = Field(
        default=None,
        description="Currency code override",
        examples=["AUD"],
    )
    attribution: Optional[str] = Field(
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
    batch_size: Optional[int] = Field(
        default=None,
        ge=1,
        description="Optional batch size for DB writes",
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "platform": "meta",
                "filenames": ["DMA_Performance_Meta.csv"],
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

    filename: str = Field(..., description="Original filename that was processed")
    file_path: Path = Field(..., description="Absolute path to the processed file")
    inserted: int = Field(..., ge=0, description="Number of new records written")
    updated: int = Field(..., ge=0, description="Number of existing rows updated")
    skipped: int = Field(..., ge=0, description="Rows skipped after validation errors")
    warnings: List[str] = Field(default_factory=list, description="Non-fatal warnings")
    status: str = Field(..., description="Overall ingestion status (ingested, dry_run, no_data, failed)")
    summary: str = Field(..., description="Human-readable description of what happened during ingestion")
    duration_sec: float = Field(..., ge=0, description="Total execution time in seconds")
    normalized_path: Path = Field(..., description="Location of the normalized CSV copy")

    model_config = {
        "json_schema_extra": {
            "example": {
                "filename": "DMA_Performance_Meta.csv",
                "file_path": "/app/data/uploads/meta/DMA_Performance_Meta.csv",
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


class SingleFileIngestionRequest(BaseModel):
    """Request payload for ingesting a specific normalized file."""

    platform: IngestionPlatform = Field(
        ..., description="Platform folder the normalized file belongs to"
    )
    filename: str = Field(
        ..., description="Filename (normalized or source) to ingest"
    )
    column_map: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Dimension or field overrides",
        examples=[{"platform_id": 1, "account_id": 10}],
    )
    currency_code: Optional[str] = Field(
        default=None,
        description="Currency code override",
        examples=["AUD"],
    )
    attribution: Optional[str] = Field(
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
    batch_size: Optional[int] = Field(
        default=None,
        ge=1,
        description="Optional batch size for DB writes",
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "platform": "tiktok",
                "filename": "tiktok_by_dma__normalized.csv",
                "column_map": {"platform_id": 1, "account_id": 10},
                "currency_code": "AUD",
                "attribution": "Incremental",
                "dry_run": False,
                "fail_fast": False,
                "batch_size": 500,
            }
        }
    }


class PlatformIngestionResponse(BaseModel):
    """Aggregated response for platform-level ingestion."""

    platform: IngestionPlatform = Field(..., description="Platform that was processed")
    results: List[FileIngestionResponse] = Field(
        ..., description="Per-file ingestion outcomes for the platform"
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "platform": "tiktok",
                "results": [
                    {
                        "filename": "tiktok_by_dma.csv",
                        "file_path": "/app/data/uploads/tiktok/tiktok_by_dma.csv",
                        "inserted": 120,
                        "updated": 5,
                        "skipped": 0,
                        "warnings": [],
                        "status": "ingested",
                        "summary": "Inserted records into the warehouse. Inserted=120, Updated=5, Skipped=0.",
                        "duration_sec": 4.05,
                        "normalized_path": "/app/data/uploads/tiktok/tiktok_by_dma__normalized.csv",
                    }
                ],
            }
        }
    }


class NormalizationRequest(BaseModel):
    """Options controlling the bulk normalization sweep."""

    platforms: Optional[List[IngestionPlatform]] = Field(
        default=None,
        description="Platforms to normalize. Defaults to every supported platform.",
        examples=[["tiktok", "shopify"]],
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "platforms": ["tiktok", "meta"],
            }
        }
    }


class NormalizedFileResult(BaseModel):
    """Metadata returned for each normalized file."""

    platform: IngestionPlatform = Field(..., description="Platform that owns the file")
    filename: str = Field(..., description="Original filename that was normalized")
    source_path: Path = Field(..., description="Path to the uploaded source file")
    normalized_path: Optional[Path] = Field(
        default=None,
        description="Location of the normalized CSV copy, when successful",
    )
    row_count: Optional[int] = Field(
        default=None, description="Number of rows present in the normalized file"
    )
    header_count: Optional[int] = Field(
        default=None, description="Number of headers detected during normalization"
    )
    encoding: Optional[str] = Field(
        default=None, description="Detected encoding for the source file"
    )
    delimiter: Optional[str] = Field(
        default=None, description="Detected delimiter for the source file"
    )
    status: str = Field(
        ..., description="Outcome of normalization (normalized, failed, skipped)"
    )
    detail: str = Field(..., description="Human-readable description of the outcome")

    model_config = {
        "json_schema_extra": {
            "example": {
                "platform": "tiktok",
                "filename": "tiktok_by_dma.csv",
                "source_path": "/app/data/uploads/tiktok/tiktok_by_dma.csv",
                "normalized_path": "/app/data/uploads/tiktok/tiktok_by_dma__normalized.csv",
                "row_count": 42867,
                "header_count": 21,
                "encoding": "latin-1",
                "delimiter": "\t",
                "status": "normalized",
                "detail": "Normalized successfully",
            }
        }
    }


class NormalizationResponse(BaseModel):
    """Aggregated response when normalizing uploaded files."""

    results: List[NormalizedFileResult] = Field(
        ..., description="Per-file normalization metadata"
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "results": [
                    {
                        "platform": "meta",
                        "filename": "DMA_Performance_Meta.csv",
                        "source_path": "/app/data/uploads/meta/DMA_Performance_Meta.csv",
                        "normalized_path": "/app/data/uploads/meta/DMA_Performance_Meta__normalized.csv",
                        "row_count": 8,
                        "header_count": 21,
                        "encoding": "utf-8",
                        "delimiter": "\t",
                        "status": "normalized",
                        "detail": "Normalized successfully",
                    }
                ]
            }
        }
    }
