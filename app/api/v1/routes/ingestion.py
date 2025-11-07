"""Endpoints supporting marketing data ingestion."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.ingestion import (
    FileIngestionRequest,
    FileIngestionResponse,
    FileUploadResponse,
)
from app.services.ingestion.service import FileIngestionService
from app.services.ingestion.types import IngestionContext

router = APIRouter(prefix="/files", tags=["files"])


@router.post("/upload", response_model=FileUploadResponse)
async def upload_file(file: UploadFile) -> FileUploadResponse:
    storage_dir = Path("data/uploads")
    storage_dir.mkdir(parents=True, exist_ok=True)
    destination = storage_dir / file.filename

    size = 0
    with destination.open("wb") as buffer:
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            buffer.write(chunk)

    return FileUploadResponse(saved_path=destination.resolve(), size_bytes=size)


@router.post("/ingest/path", response_model=FileIngestionResponse)
async def ingest_file_by_path(
    payload: FileIngestionRequest,
    session: AsyncSession = Depends(get_db),
) -> FileIngestionResponse:
    if not payload.file_path.exists():
        raise HTTPException(status_code=404, detail="file_path does not exist")

    context = IngestionContext(
        file_path=payload.file_path,
        normalized_path=payload.file_path,
        column_map=payload.column_map or {},
        currency_code=payload.currency_code,
        attribution=payload.attribution,
        dry_run=payload.dry_run,
        fail_fast=payload.fail_fast,
        batch_size=payload.batch_size or 500,
    )

    service = FileIngestionService()
    result = await service.ingest(session, context)
    return FileIngestionResponse(
        inserted=result.inserted,
        updated=result.updated,
        skipped=result.skipped,
        warnings=result.warnings,
        duration_sec=result.duration_seconds,
        normalized_path=context.normalized_path,
    )
