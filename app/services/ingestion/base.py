"""Base classes for ingestion handlers."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.marketing import DimAttribution
from app.services.ingestion.types import IngestionContext, IngestionResult
from app.services.ingestion.utils import NormalizationResult


class IngestionHandler(ABC):
    """Contract implemented by individual file handlers."""

    @abstractmethod
    def matches(self, file_path: str) -> bool:
        """Return True if this handler can process the file."""

    @abstractmethod
    async def validate(self, normalized: NormalizationResult, context: IngestionContext) -> None:
        """Validate the normalized content before ingestion."""

    @abstractmethod
    async def ingest(
        self,
        session: AsyncSession,
        normalized: NormalizationResult,
        context: IngestionContext,
    ) -> IngestionResult:
        """Perform the ingestion and return a result summary."""

    async def _resolve_attribution_id(
        self, session: AsyncSession, context: IngestionContext
    ) -> int | None:
        if not context.attribution:
            attribution_id = context.column_map.get("attribution_id")
            if isinstance(attribution_id, int):
                return attribution_id
            return None

        stmt = select(DimAttribution).where(DimAttribution.window_type == context.attribution)
        result = await session.execute(stmt)
        attribution = result.scalar_one_or_none()
        if attribution:
            return attribution.attribution_id
        return None

    def _ensure_required_columns(
        self, normalized: NormalizationResult, required: Iterable[str]
    ) -> None:
        missing = [column for column in required if column not in normalized.headers]
        if missing:
            raise ValueError(f"Missing required columns: {', '.join(sorted(missing))}")
