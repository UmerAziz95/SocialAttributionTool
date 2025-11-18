"""Endpoints supporting marketing data ingestion."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.ingestion import (
    FileIngestionRequest,
    FileIngestionResponse,
    IngestionPlatform,
    SingleFileIngestionRequest,
    MultiFileUploadResponse,
    NormalizationRequest,
    NormalizationResponse,
    NormalizedFileResult,
    PlatformIngestionResponse,
    UploadedFileMetadata,
)
from app.services.ingestion.logging import log_event
from app.services.ingestion.storage import resolve_uploaded_path
from app.services.ingestion.service import FileIngestionService
from app.services.ingestion.types import IngestionContext
from app.services.ingestion.utils import normalize_file
from app.services.platforms.registry import get_ingestion_service_for_file

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
    response_model=MultiFileUploadResponse,
    summary="Upload one or more files for a platform",
    description=(
        "Upload one or more raw marketing exports and specify which platform they "
        "belong to (TikTok, Shopify, Meta, Pinterest, or Google). The API saves "
        "each file under a platform-specific directory and returns metadata that "
        "can be referenced when triggering ingestion."
    ),
    response_description="Metadata for each uploaded file grouped by platform.",
    status_code=201,
)
async def upload_files(
    platform: IngestionPlatform = Form(
        ...,
        description="Platform name that determines the upload subdirectory",
        examples=["tiktok", "shopify"],
    ),
    files: list[UploadFile] = File(
        ..., description="One or more CSV/TSV exports to store on the server"
    ),
) -> MultiFileUploadResponse:
    if not files:
        raise HTTPException(status_code=400, detail="At least one file must be provided")

    platform_dir = Path("data/uploads") / platform.value
    platform_dir.mkdir(parents=True, exist_ok=True)

    saved_files: list[UploadedFileMetadata] = []
    for upload in files:
        log_event(
            "UPLOAD_START",
            platform=platform.value,
            filename=upload.filename,
            content_type=upload.content_type,
        )
        destination = platform_dir / upload.filename
        size = 0
        chunks = 0
        with destination.open("wb") as buffer:
            while chunk := await upload.read(1024 * 1024):
                size += len(chunk)
                buffer.write(chunk)
                chunks += 1

        resolved_path = destination.resolve()
        log_event(
            "UPLOAD_STREAM_COMPLETE",
            platform=platform.value,
            filename=upload.filename,
            path=resolved_path,
            chunks_written=chunks,
            total_bytes=size,
        )
        log_event(
            "UPLOAD_COMPLETE",
            platform=platform.value,
            filename=upload.filename,
            path=resolved_path,
            size_bytes=size,
        )
        saved_files.append(
            UploadedFileMetadata(
                filename=upload.filename,
                saved_path=resolved_path,
                size_bytes=size,
            )
        )

    return MultiFileUploadResponse(platform=platform, files=saved_files)
@router.post(
    "/normalize",
    response_model=NormalizationResponse,
    summary="Normalize uploaded files across platforms",
    description=(
        "Scan each platform's upload directory (or a requested subset of platforms) "
        "and create normalized UTF-8 CSV copies beside the originals."
    ),
    response_description="Normalization metadata for each processed file.",
)
async def normalize_uploaded_files(
    payload: NormalizationRequest | None = Body(
        default=None,
        description="Optional payload to scope normalization to certain platforms",
    ),
) -> NormalizationResponse:
    request_payload = payload or NormalizationRequest()
    requested_platforms = request_payload.platforms or list(IngestionPlatform)
    base_dir = Path("data/uploads")
    results: list[NormalizedFileResult] = []

    for platform in requested_platforms:
        platform_dir = (base_dir / platform.value).resolve()
        if not platform_dir.exists() or not platform_dir.is_dir():
            log_event(
                "NORMALIZE_PLATFORM_SKIPPED",
                platform=platform.value,
                reason="missing_directory",
            )
            continue

        candidate_paths = [
            path
            for path in sorted(platform_dir.iterdir())
            if path.is_file() and not path.name.endswith("__normalized.csv")
        ]

        if not candidate_paths:
            log_event(
                "NORMALIZE_PLATFORM_SKIPPED",
                platform=platform.value,
                reason="no_source_files",
            )
            continue

        for file_path in candidate_paths:
            log_event(
                "NORMALIZATION_SWEEP_START",
                platform=platform.value,
                file=file_path,
            )
            try:
                normalization = normalize_file(file_path)
            except HTTPException as exc:
                log_event(
                    "NORMALIZATION_SWEEP_FAILED",
                    platform=platform.value,
                    file=file_path,
                    error=exc.detail,
                )
                results.append(
                    NormalizedFileResult(
                        platform=platform,
                        filename=file_path.name,
                        source_path=file_path,
                        normalized_path=None,
                        row_count=None,
                        header_count=None,
                        encoding=None,
                        delimiter=None,
                        status="failed",
                        detail=str(exc.detail),
                    )
                )
                continue
            except Exception as exc:  # pragma: no cover - defensive logging
                log_event(
                    "NORMALIZATION_SWEEP_FAILED",
                    platform=platform.value,
                    file=file_path,
                    error=str(exc),
                )
                results.append(
                    NormalizedFileResult(
                        platform=platform,
                        filename=file_path.name,
                        source_path=file_path,
                        normalized_path=None,
                        row_count=None,
                        header_count=None,
                        encoding=None,
                        delimiter=None,
                        status="failed",
                        detail=str(exc),
                    )
                )
                continue

            log_event(
                "NORMALIZATION_SWEEP_COMPLETE",
                platform=platform.value,
                file=file_path,
                normalized_path=normalization.path,
                row_count=len(normalization.rows),
            )
            results.append(
                NormalizedFileResult(
                    platform=platform,
                    filename=file_path.name,
                    source_path=file_path,
                    normalized_path=normalization.path,
                    row_count=len(normalization.rows),
                    header_count=len(normalization.headers),
                    encoding=normalization.encoding,
                    delimiter=normalization.delimiter,
                    status="normalized",
                    detail="Normalized successfully",
                )
            )

    if not results:
        raise HTTPException(
            status_code=404,
            detail="No uploaded files were found to normalize for the requested platforms",
        )

    return NormalizationResponse(results=results)


@router.post(
    "/ingest/file",
    response_model=FileIngestionResponse,
    summary="Ingest a specific normalized file",
    description=(
        "Trigger ingestion for a single normalized artifact by specifying the "
        "platform and filename. The API looks for the __normalized.csv copy "
        "and skips the normalization step."
    ),
)
async def ingest_single_file(
    payload: SingleFileIngestionRequest,
    session: AsyncSession = Depends(get_db),
) -> FileIngestionResponse:
    service = get_ingestion_service_for_file(payload.platform, payload.filename)
    if not service:
        raise HTTPException(
            status_code=404,
            detail=(
                "No ingestion service is registered for this platform/filename "
                "combination"
            ),
        )

    log_event(
        "INGEST_SINGLE_FILE_REQUEST",
        platform=payload.platform.value,
        filename=payload.filename,
        dry_run=payload.dry_run,
        fail_fast=payload.fail_fast,
        batch_size=payload.batch_size or 500,
    )
    result, context = await service.ingest(
        session,
        filename=payload.filename,
        column_map=payload.column_map or {},
        currency_code=payload.currency_code,
        attribution=payload.attribution,
        dry_run=payload.dry_run,
        fail_fast=payload.fail_fast,
        batch_size=payload.batch_size or 500,
    )
    normalized_path = context.normalized_path or context.file_path
    return FileIngestionResponse(
        filename=payload.filename,
        file_path=context.file_path,
        inserted=result.inserted,
        updated=result.updated,
        skipped=result.skipped,
        warnings=result.warnings,
        status=result.status,
        summary=result.summary,
        duration_sec=result.duration_seconds,
        normalized_path=normalized_path,
    )


@router.post(
    "/ingest/platform",
    response_model=PlatformIngestionResponse,
    summary="Ingest every uploaded file for a platform",
    description=(
        "Trigger normalization and database ingestion for every file stored in a "
        "platform's upload directory (or a provided subset). The server writes "
        "normalized copies beside each source file using the __normalized suffix."
    ),
    response_description="Per-file ingestion results for the selected platform.",
)
async def ingest_platform_files(
    payload: FileIngestionRequest,
    session: AsyncSession = Depends(get_db),
) -> PlatformIngestionResponse:
    platform_dir = (Path("data/uploads") / payload.platform.value).resolve()
    if not platform_dir.exists() or not platform_dir.is_dir():
        raise HTTPException(
            status_code=404,
            detail=(
                f"No uploads found for platform '{payload.platform.value}'. Upload files "
                "before triggering ingestion."
            ),
        )

    requested_files = payload.filenames
    candidate_paths: list[Path] = []
    if requested_files:
        for name in requested_files:
            candidate_paths.append(resolve_uploaded_path(name, payload.platform))
    else:
        candidate_paths = [
            path
            for path in sorted(platform_dir.iterdir())
            if path.is_file() and not path.name.endswith("__normalized.csv")
        ]

    if not candidate_paths:
        raise HTTPException(
            status_code=404,
            detail="No matching files found to ingest for this platform",
        )

    service = FileIngestionService()
    results: list[FileIngestionResponse] = []
    for file_path in candidate_paths:
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
        log_event(
            "INGEST_REQUEST",
            platform=payload.platform.value,
            file=file_path,
            currency_code=context.currency_code,
            attribution=context.attribution,
            dry_run=context.dry_run,
            fail_fast=context.fail_fast,
            batch_size=context.batch_size,
            column_map=context.column_map,
        )
        result = await service.ingest(session, context)
        results.append(
            FileIngestionResponse(
                filename=file_path.name,
                file_path=file_path,
                inserted=result.inserted,
                updated=result.updated,
                skipped=result.skipped,
                warnings=result.warnings,
                status=result.status,
                summary=result.summary,
                duration_sec=result.duration_seconds,
                normalized_path=context.normalized_path,
            )
        )

    return PlatformIngestionResponse(platform=payload.platform, results=results)
