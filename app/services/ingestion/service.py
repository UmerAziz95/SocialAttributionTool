"""High level service orchestrating file ingestion."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Iterable

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.marketing import EventIngestionLog
from app.services.ingestion.handlers import HANDLERS
from app.services.ingestion.logging import get_ingestion_logger
from app.services.ingestion.types import IngestionContext, IngestionResult
from app.services.ingestion.utils import NormalizationResult, normalize_file


class FileIngestionService:
    def __init__(self, handlers: Iterable = HANDLERS):
        self._handlers = list(handlers)
        self._logger = get_ingestion_logger()

    def _select_handler(self, file_path: Path):
        for handler in self._handlers:
            if handler.matches(file_path.name):
                self._logger.info(
                    "HANDLER_SELECTED | file=%s | handler=%s",
                    file_path,
                    handler.__class__.__name__,
                )
                return handler
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {file_path.name}")

    async def ingest(
        self,
        session: AsyncSession,
        context: IngestionContext,
    ) -> IngestionResult:
        self._logger.info(
            "INGEST_START | file=%s | dry_run=%s",
            context.file_path,
            context.dry_run,
        )
        handler = self._select_handler(context.file_path)
        self._logger.info("NORMALIZATION_BEGIN | file=%s", context.file_path)
        normalized: NormalizationResult = normalize_file(context.file_path)
        context.normalized_path = normalized.path
        self._logger.info(
            "NORMALIZATION_COMPLETE | file=%s | normalized=%s | encoding=%s | delimiter=%s | rows=%s",
            context.file_path,
            normalized.path,
            normalized.encoding,
            normalized.delimiter,
            len(normalized.rows),
        )

        self._logger.info("VALIDATION_BEGIN | handler=%s", handler.__class__.__name__)
        await handler.validate(normalized, context)
        self._logger.info("VALIDATION_COMPLETE | handler=%s", handler.__class__.__name__)

        status = "success"
        error_message: str | None = None
        try:
            self._logger.info("INGESTION_BEGIN | handler=%s", handler.__class__.__name__)
            result = await handler.ingest(session, normalized, context)
            self._logger.info(
                "INGESTION_COMPLETE | handler=%s | inserted=%s | updated=%s | skipped=%s",
                handler.__class__.__name__,
                result.inserted,
                result.updated,
                result.skipped,
            )
        except Exception as exc:  # noqa: BLE001
            status = "failed"
            error_message = str(exc)
            result = IngestionResult()
            result.warnings.append(str(exc))
            result.finished_at = datetime.utcnow()
            self._logger.exception(
                "INGESTION_FAILED | handler=%s | error=%s",
                handler.__class__.__name__,
                exc,
            )
            await self._log_event(session, context, result, status, error_message)
            raise
        else:
            result.finished_at = datetime.utcnow()
            await self._log_event(session, context, result, status, error_message)
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
        self._logger.info(
            "EVENT_LOG | platform_id=%s | status=%s | records=%s | duration=%s | error=%s",
            platform_id,
            status,
            records_fetched,
            duration,
            error_message,
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
