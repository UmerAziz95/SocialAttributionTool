"""Endpoints supporting marketing data ingestion."""
from __future__ import annotations

from pathlib import Path, PureWindowsPath

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.ingestion import (
    FileIngestionRequest,
    FileIngestionResponse,
    FileUploadResponse,
)
from app.services.ingestion.logging import get_ingestion_logger, log_event
from app.services.ingestion.service import FileIngestionService
from app.services.ingestion.types import IngestionContext

logger = get_ingestion_logger()

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
    log_event(
        "UPLOAD_START",
        filename=file.filename,
        content_type=file.content_type,
    )
    storage_dir = Path("data/uploads")
    storage_dir.mkdir(parents=True, exist_ok=True)
    destination = storage_dir / file.filename

    size = 0
    with destination.open("wb") as buffer:
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            buffer.write(chunk)

    resolved_path = destination.resolve()
    log_event(
        "UPLOAD_COMPLETE",
        filename=file.filename,
        path=resolved_path,
        size_bytes=size,
    )
    return FileUploadResponse(saved_path=resolved_path, size_bytes=size)


def _resolve_uploaded_path(provided: Path | str) -> Path:
    """Locate an uploaded file based on the provided path or filename.

    The upload endpoint returns an absolute path, but users may also supply just the
    filename or a path that differs from the server's runtime root (for example when
    following documentation examples). This helper searches a few sensible locations
    so ingestion succeeds as long as the file exists within the uploads directory.
    """

    raw_value = str(provided).strip()
    if not raw_value:
        raise HTTPException(status_code=400, detail="file_path must be provided")
    storage_dir = Path("data/uploads").resolve()
    normalized = raw_value.replace("\\", "/")

    candidates: list[Path] = []
    seen: set[str] = set()

    def add_candidate(path: Path) -> None:
        candidate_str = str(path)
        if not candidate_str or candidate_str in seen:
            return
        candidates.append(path)
        seen.add(candidate_str)

    # 1. Use the path as provided (works for absolute/relative POSIX paths).
    add_candidate(Path(raw_value))

    # 2. Attempt to interpret Windows-style inputs (drive letters or backslashes).
    if "\\" in raw_value or ":" in raw_value:
        add_candidate(Path(PureWindowsPath(raw_value)))

    # 3. If the path already contains the uploads directory, align it with the
    #    actual runtime storage root.
    marker = "/data/uploads/"
    if marker in normalized:
        suffix = normalized.split(marker, 1)[1]
        add_candidate(storage_dir / suffix)

    # 4. Finally, fall back to matching on the filename only.
    filename = Path(normalized).name
    if filename:
        add_candidate(storage_dir / filename)

    for candidate in candidates:
        try:
            candidate_path = candidate if candidate.is_absolute() else candidate.resolve()
        except OSError:
            continue

        if candidate_path.exists():
            log_event(
                "RESOLVE_PATH_SUCCESS",
                provided=raw_value,
                resolved=candidate_path,
            )
            return candidate_path

    logger.warning(
        "RESOLVE_PATH_FAILED | provided=%s | searched=%s",
        raw_value,
        ", ".join(str(c) for c in candidates),
    )
    raise HTTPException(
        status_code=404,
        detail=f"file_path '{raw_value}' does not exist in expected upload directories",
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
    log_event(
        "INGEST_REQUEST",
        file=file_path,
        currency_code=context.currency_code,
        attribution=context.attribution,
        dry_run=context.dry_run,
        fail_fast=context.fail_fast,
        batch_size=context.batch_size,
        column_map=context.column_map,
    )
    result = await service.ingest(session, context)
    return FileIngestionResponse(
        inserted=result.inserted,
        updated=result.updated,
        skipped=result.skipped,
        warnings=result.warnings,
        duration_sec=result.duration_seconds,
        normalized_path=context.normalized_path,
    )
