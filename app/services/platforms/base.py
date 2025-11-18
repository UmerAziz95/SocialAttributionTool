"""Shared helpers for platform/file-specific services."""
from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.files.base import PlatformFileRepository
from app.services.ingestion.service import FileIngestionService
from app.services.ingestion.types import IngestionContext, IngestionResult
from app.services.ingestion.utils import NormalizationResult, normalize_file


class BasePlatformService:
    def __init__(self, repository: PlatformFileRepository) -> None:
        self._repository = repository


class FileNormalizationService(BasePlatformService):
    """Normalizes a single file tied to a repository."""

    def normalize(self, filename: str | None = None) -> NormalizationResult:
        source = self._repository.resolve_source(filename)
        return normalize_file(source)


class PlatformFileIngestionService(BasePlatformService):
    """Ingests a normalized file via the shared FileIngestionService."""

    def __init__(
        self,
        repository: PlatformFileRepository,
        ingestion_service: FileIngestionService | None = None,
    ) -> None:
        super().__init__(repository)
        self._ingestion = ingestion_service or FileIngestionService()

    async def ingest(
        self,
        session: AsyncSession,
        *,
        filename: str | None = None,
        column_map: dict[str, Any] | None = None,
        currency_code: str | None = None,
        attribution: str | None = None,
        dry_run: bool = False,
        fail_fast: bool = False,
        batch_size: int = 500,
    ) -> tuple[IngestionResult, IngestionContext]:
        normalized_path = self._repository.resolve_normalized(filename)
        context = IngestionContext(
            file_path=normalized_path,
            normalized_path=normalized_path,
            column_map=column_map or {},
            currency_code=currency_code,
            attribution=attribution,
            dry_run=dry_run,
            fail_fast=fail_fast,
            batch_size=batch_size,
            use_existing_normalized=True,
        )
        result = await self._ingestion.ingest(session, context)
        return result, context


__all__ = [
    "BasePlatformService",
    "FileNormalizationService",
    "PlatformFileIngestionService",
]
