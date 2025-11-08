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

router = APIRouter(
    prefix="/files",
    tags=["files"],
    responses={
        422: {
            "description": "Validation error",
            "content": {"application/json": {"example": {"detail": "..."}}},
        }
    },
)


@router.post(
    "/upload",
    response_model=FileUploadResponse,
    summary="Upload a source file",
    description=(
        "Upload a raw marketing export. The API writes the file to the server "
        "storage directory and returns the fully-qualified path so it can be "
        "referenced in the ingestion request."
    ),
    response_description="Metadata for the uploaded file including its storage path.",
    status_code=201,
)
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


def _resolve_uploaded_path(provided: Path) -> Path:
    """Locate an uploaded file based on the provided path or filename.

    The upload endpoint returns an absolute path, but users may also supply just the
    filename or a path that differs from the server's runtime root (for example when
    following documentation examples). This helper searches a few sensible locations
    so ingestion succeeds as long as the file exists within the uploads directory.
    """

    storage_dir = Path("data/uploads").resolve()
    candidates: list[Path] = []

    if provided.is_absolute():
        candidates.append(provided)
    else:
        candidates.append((Path.cwd() / provided).resolve())

    if provided.name:
        candidates.append(storage_dir / provided.name)

    if not provided.is_absolute():
        candidates.append(storage_dir / provided)

    seen: set[str] = set()
    for candidate in candidates:
        candidate_str = str(candidate)
        if candidate_str in seen:
            continue
        seen.add(candidate_str)
        if candidate.exists():
            return candidate

    raise HTTPException(
        status_code=404,
        detail="file_path does not exist in expected upload directories",
    )


@router.post(
    "/ingest/path",
    response_model=FileIngestionResponse,
    summary="Ingest a previously uploaded file",
    description=(
        "Trigger normalization and database ingestion for a file saved on the "
        "server. Provide optional overrides such as currency code, attribution "
        "window, or dimension IDs."
    ),
    response_description="Result of the ingestion run, including counts and warnings.",
)
async def ingest_file_by_path(
    payload: FileIngestionRequest,
    session: AsyncSession = Depends(get_db),
) -> FileIngestionResponse:
    file_path = _resolve_uploaded_path(payload.file_path)

    context = IngestionContext(
        file_path=file_path,
        normalized_path=file_path,
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
