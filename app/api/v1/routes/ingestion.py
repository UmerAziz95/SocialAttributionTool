"""Endpoints supporting marketing data ingestion."""
from __future__ import annotations

from pathlib import Path, PureWindowsPath

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.ingestion import (
    FileIngestionRequest,
    FileIngestionResponse,
    IngestionPlatform,
    MultiFileUploadResponse,
    NormalizationRequest,
    NormalizationResponse,
    NormalizedFileResult,
    PlatformIngestionResponse,
    UploadedFileMetadata,
)
from app.services.ingestion.logging import get_ingestion_logger, log_event
from app.services.ingestion.service import FileIngestionService
from app.services.ingestion.types import IngestionContext
from app.services.ingestion.utils import normalize_file

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


def _resolve_uploaded_path(
    provided: Path | str, platform: IngestionPlatform | None = None
) -> Path:
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
    platform_dir = storage_dir / platform.value if platform else None
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

    # 4. If a platform is provided and the path is relative, scope the lookup to
    #    the corresponding subdirectory.
    if platform_dir and not Path(raw_value).is_absolute():
        add_candidate(platform_dir / raw_value)

    # 4. Finally, fall back to matching on the filename only.
    filename = Path(normalized).name
    if filename:
        if platform_dir:
            add_candidate(platform_dir / filename)
        else:
            add_candidate(storage_dir / filename)
        # Search all platform subdirectories for a matching filename.
        try:
            for subdir in storage_dir.iterdir():
                if not subdir.is_dir():
                    continue
                add_candidate(subdir / filename)
        except FileNotFoundError:
            pass

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
            candidate_paths.append(_resolve_uploaded_path(name, payload.platform))
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
