"""Helpers for resolving dimension identifiers used during ingestion."""
from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.marketing import DimDate


class DimensionResolver:
    """Utility that resolves dimension identifiers using the provided column map."""

    def __init__(self, column_map: dict[str, Any] | None = None):
        self.column_map = column_map or {}

    def require(self, key: str) -> Any:
        if key not in self.column_map:
            raise KeyError(f"column_map missing required key '{key}'")
        return self.column_map[key]

    def optional(self, key: str, default: Any | None = None) -> Any:
        return self.column_map.get(key, default)

    def resolve_mapping(self, key: str, raw_value: str) -> Any | None:
        mapping = self.column_map.get(key)
        if not mapping:
            return None
        normalized = (raw_value or "").strip().lower()
        return mapping.get(normalized)


async def ensure_date_id(session: AsyncSession, target_date: date) -> int:
    date_id = int(target_date.strftime("%Y%m%d"))
    stmt = select(DimDate.date_id).where(DimDate.date_id == date_id)
    result = await session.execute(stmt)
    existing = result.scalar_one_or_none()
    if existing:
        return existing

    await session.execute(
        insert(DimDate)
        .values(
            date_id=date_id,
            date_actual=target_date,
            week=target_date.isocalendar()[1],
            month=target_date.month,
            quarter=((target_date.month - 1) // 3) + 1,
            year=target_date.year,
        )
        .on_conflict_do_nothing(index_elements=[DimDate.date_id])
    )
    await session.flush()
    return date_id
