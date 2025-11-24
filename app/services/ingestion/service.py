"""High level service orchestrating file ingestion."""
from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Iterable

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.marketing import EventIngestionLog
from app.services.ingestion.handlers import HANDLERS
from app.services.ingestion.logging import get_ingestion_logger, log_event
from app.services.ingestion.types import IngestionContext, IngestionResult
from app.services.ingestion.utils import (
    NormalizationResult,
    load_normalized_artifact,
    normalize_file,
)


class FileIngestionService:
    def __init__(self, handlers: Iterable = HANDLERS):
        self._handlers = list(handlers)
        self._logger = get_ingestion_logger()

    def _select_handler(self, file_path: Path):
        for handler in self._handlers:
            if handler.matches(file_path.name):
                log_event(
                    "HANDLER_SELECTED",
                    file=file_path,
                    handler=handler.__class__.__name__,
                )
                return handler
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {file_path.name}")

    async def ingest(
        self,
        session: AsyncSession,
        context: IngestionContext,
    ) -> IngestionResult:
        log_event(
            "STAGE_START",
            stage="ingestion_pipeline",
            description="Beginning ingestion orchestration",
            file=context.file_path,
        )
        log_event(
            "INGEST_START",
            file=context.file_path,
            dry_run=context.dry_run,
            column_map=context.column_map,
            currency_code=context.currency_code,
            attribution=context.attribution,
        )
        handler = self._select_handler(context.file_path)
        log_event(
            "STAGE_START",
            stage="normalization",
            description="Detecting encoding/delimiter and preparing normalized copy",
            file=context.file_path,
        )
        log_event("NORMALIZATION_BEGIN", file=context.file_path)
        if context.use_existing_normalized:
            if not context.normalized_path:
                raise HTTPException(
                    status_code=400,
                    detail="normalized_path must be provided when reusing normalized files",
                )
            normalized = load_normalized_artifact(context.normalized_path)
            log_event(
                "NORMALIZATION_REUSED",
                source=context.normalized_path,
                row_count=len(normalized.rows),
                headers=normalized.headers,
            )
        else:
            normalized = normalize_file(context.file_path)
            context.normalized_path = normalized.path
            log_event(
                "NORMALIZATION_COMPLETE",
                source=context.file_path,
                normalized=normalized.path,
                encoding=normalized.encoding,
                delimiter=normalized.delimiter,
                row_count=len(normalized.rows),
                headers=normalized.headers,
            )
        log_event(
            "STAGE_COMPLETE",
            stage="normalization",
            normalized_path=context.normalized_path,
            row_count=len(normalized.rows),
            header_count=len(normalized.headers),
        )

        log_event(
            "VALIDATION_BEGIN",
            handler=handler.__class__.__name__,
            file=context.file_path,
            normalized=context.normalized_path,
        )
        log_event( 
            "STAGE_START",
            stage="validation",
            description="Running handler validation checks",
            handler=handler.__class__.__name__,
            file=context.file_path,
        ) 
        await handler.validate(normalized, context)
        log_event(
            "VALIDATION_COMPLETE",
            handler=handler.__class__.__name__,
            file=context.file_path,
        )
        log_event(
            "STAGE_COMPLETE",
            stage="validation",
            handler=handler.__class__.__name__,
            file=context.file_path,
        )

        status = "success"
        error_message: str | None = None
        try:
            log_event(
                "INGESTION_BEGIN",
                handler=handler.__class__.__name__,
                file=context.file_path,
                normalized=context.normalized_path,
            )
            log_event(
                "STAGE_START",
                stage="database_write",
                description="Delegating to handler ingest routine",
                handler=handler.__class__.__name__,
                normalized=context.normalized_path,
            )
            result = await handler.ingest(session, normalized, context)
            log_event(
                "INGESTION_COMPLETE",
                handler=handler.__class__.__name__,
                file=context.file_path,
                inserted=result.inserted,
                updated=result.updated,
                skipped=result.skipped,
                warnings=result.warnings,
            )
            log_event(
                "INGESTION_FILE_SUMMARY",
                handler=handler.__class__.__name__,
                file=context.file_path,
                normalized=context.normalized_path,
                inserted=result.inserted,
                updated=result.updated,
                skipped=result.skipped,
                warnings_count=len(result.warnings),
                status=result.status,
            )
            log_event(
                "STAGE_COMPLETE",
                stage="database_write",
                handler=handler.__class__.__name__,
                inserted=result.inserted,
                updated=result.updated,
                skipped=result.skipped,
            )
        except Exception as exc:  # noqa: BLE001
            status = "failed"
            error_message = str(exc)
            result = IngestionResult()
            result.warnings.append(str(exc))
            result.finished_at = datetime.utcnow()
            result.status = status
            result.summary = (
                f"Handler failed: {error_message}" if error_message else "Handler failed."
            )
            await session.rollback()
            log_event(
                "INGESTION_ERROR",
                level=logging.ERROR,
                handler=handler.__class__.__name__,
                file=context.file_path,
                error=error_message,
            ) 
            log_event(
                "STAGE_COMPLETE",
                stage="database_write",
                status="failed",
                handler=handler.__class__.__name__,
                error=error_message,
            )
            self._logger.exception(
                "INGESTION_FAILED | handler=%s | error=%s",
                handler.__class__.__name__,
                exc,
            )
            await self._log_event(session, context, result, status, error_message)
            log_event(
                "STAGE_COMPLETE",
                stage="ingestion_pipeline",
                status=status,
                summary=result.summary,
            )
            raise
        else:
            result.finished_at = datetime.utcnow()
            if context.dry_run:
                status = "dry_run"
            elif result.inserted or result.updated:
                status = "ingested"
            else:
                status = "no_data"
            result.status = status
            if not result.summary:
                action = {
                    "dry_run": "Dry run completed",
                    "ingested": "Inserted records into the warehouse",
                    "no_data": "No rows were written",
                }.get(status, "Ingestion completed")
                result.summary = (
                    f"{action}. Inserted={result.inserted}, Updated={result.updated}, Skipped={result.skipped}."
                )
            await self._log_event(session, context, result, status, error_message)
            log_event(
                "STAGE_COMPLETE",
                stage="ingestion_pipeline",
                status=status,
                summary=result.summary,
                duration_seconds=result.duration_seconds,
            )
            return result

    async def _log_event(                
        self,
        session: AsyncSession,
        context: IngestionContext,
        result: IngestionResult,
        status: str,
        error_message: str | None,
    ) -> None:
        platform_id = context.column_map.get("platform_id")
        records_fetched = result.inserted + result.updated
        duration = Decimal(str(result.duration_seconds))
        log_event(
            "EVENT_LOG_WRITE",
            platform_id=platform_id,
            status=status,
            records=records_fetched,
            duration_seconds=duration,
            error=error_message,
            summary=result.summary,
        )                         
        log_event(
            "EVENT_LOG_DB_WRITE_BEGIN",
            platform_id=platform_id,
            status=status,
        )
        session.add(
            EventIngestionLog(
                platform_id=platform_id,
                records_fetched=records_fetched,
                status=status,
                error_message=error_message,
                duration_seconds=duration,
            )
        )
        await session.commit()
        log_event(
            "EVENT_LOG_DB_WRITE_COMPLETE",
            platform_id=platform_id,
            status=status,
        )
