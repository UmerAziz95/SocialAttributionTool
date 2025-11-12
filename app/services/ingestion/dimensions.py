"""Helpers for resolving dimension identifiers used during ingestion."""
from __future__ import annotations

from datetime import date
import re
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.marketing import (
    DimAd,
    DimAdsetOrAdgroup,
    DimAccount,
    DimCampaign,
    DimDMA,
    DimDate,
    DimPlatform,
    MapPlatformDMA,
)


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


async def ensure_platform_id(
    session: AsyncSession,
    platform_id: int,
    *,
    name: str | None = None,
) -> int:
    """Ensure a platform dimension exists for the supplied identifier."""

    existing = await session.get(DimPlatform, platform_id)
    if existing:
        return existing.platform_id

    platform = DimPlatform(platform_id=platform_id, name=name or f"Platform {platform_id}")
    session.add(platform)
    await session.flush()
    return platform.platform_id


async def _generate_unique_dma_code(session: AsyncSession, base_label: str) -> str:
    """Return a unique DMA code derived from the provided label."""

    slug = re.sub(r"[^A-Za-z0-9]+", "_", base_label).strip("_").upper()
    if not slug:
        slug = "DMA"

    candidate = slug
    suffix = 1
    while True:
        stmt = select(DimDMA.dma_id).where(DimDMA.dma_code == candidate).limit(1)
        existing = (await session.execute(stmt)).scalar_one_or_none()
        if existing is None:
            return candidate
        candidate = f"{slug}_{suffix}"
        suffix += 1


async def ensure_dma_id(
    session: AsyncSession,
    platform_id: int,
    *,
    label: str,
) -> int | None:
    """Ensure a DMA exists for the supplied platform-specific label."""

    normalized_label = " ".join(label.strip().split())
    if not normalized_label:
        return None

    # Check for an existing platform-specific mapping first.
    stmt = (
        select(MapPlatformDMA.dma_id)
        .where(
            MapPlatformDMA.platform_id == platform_id,
            func.lower(MapPlatformDMA.platform_dma_label)
            == normalized_label.lower(),
        )
        .limit(1)
    )
    existing_dma_id = (await session.execute(stmt)).scalar_one_or_none()
    if existing_dma_id is not None:
        return existing_dma_id

    # Look for an existing DMA dimension by name.
    stmt = (
        select(DimDMA)
        .where(func.lower(DimDMA.dma_name) == normalized_label.lower())
        .limit(1)
    )
    existing_dma = (await session.execute(stmt)).scalar_one_or_none()

    if existing_dma is None:
        dma_code = await _generate_unique_dma_code(session, normalized_label)
        existing_dma = DimDMA(dma_code=dma_code, dma_name=normalized_label)
        session.add(existing_dma)
        await session.flush()

    dma_id = existing_dma.dma_id

    # Persist the platform mapping so subsequent ingestions reuse it.
    stmt = (
        select(MapPlatformDMA.id)
        .where(
            MapPlatformDMA.platform_id == platform_id,
            func.lower(MapPlatformDMA.platform_dma_label)
            == normalized_label.lower(),
        )
        .limit(1)
    )
    existing_mapping = (await session.execute(stmt)).scalar_one_or_none()
    if existing_mapping is None:
        mapping = MapPlatformDMA(
            platform_id=platform_id,
            platform_dma_label=normalized_label,
            dma_id=dma_id,
        )
        session.add(mapping)
        await session.flush()

    return dma_id


async def ensure_account_id(
    session: AsyncSession,
    account_id: int,
    platform_id: int,
    *,
    external_id: str | None = None,
    name: str | None = None,
) -> int:
    """Ensure an account dimension exists for the given identifier."""

    stmt = select(DimAccount.account_id).where(DimAccount.account_id == account_id).limit(1)
    result = await session.execute(stmt)
    existing = result.scalar_one_or_none()
    if existing:
        return existing

    insert_values = {
        "account_id": account_id,
        "platform_id": platform_id,
        "external_account_id": external_id,
        "account_name": name,
    }

    await session.execute(
        insert(DimAccount)
        .values(**insert_values)
        .on_conflict_do_nothing(index_elements=[DimAccount.account_id])
    )
    await session.flush()
    return account_id


async def ensure_campaign_id(
    session: AsyncSession,
    account_id: int,
    *,
    external_id: str | None = None,
    name: str | None = None,
) -> int:
    """Return the campaign identifier for the provided account/name pair.

    Campaign dimensions are looked up by `external_campaign_id` first (when the
    source file provides an explicit identifier) and then by the campaign name.
    When the campaign does not yet exist, a new row is created so fact rows can
    reference it.
    """

    if external_id:
        stmt = (
            select(DimCampaign.campaign_id)
            .where(
                DimCampaign.account_id == account_id,
                DimCampaign.external_campaign_id == external_id,
            )
            .limit(1)
        )
        result = await session.execute(stmt)
        existing = result.scalar_one_or_none()
        if existing:
            return existing

    if name:
        stmt = (
            select(DimCampaign.campaign_id)
            .where(
                DimCampaign.account_id == account_id,
                DimCampaign.campaign_name == name,
            )
            .limit(1)
        )
        result = await session.execute(stmt)
        existing = result.scalar_one_or_none()
        if existing:
            return existing

    insert_values = {
        "account_id": account_id,
        "external_campaign_id": external_id,
        "campaign_name": name,
    }
    result = await session.execute(
        insert(DimCampaign)
        .values(**insert_values)
        .returning(DimCampaign.campaign_id)
    )
    campaign_id = result.scalar_one()
    await session.flush()
    return campaign_id


async def ensure_adset_id(
    session: AsyncSession,
    campaign_id: int,
    *,
    external_id: str | None = None,
    name: str | None = None,
) -> int:
    """Return the ad set identifier for the provided campaign/name pair."""

    if external_id:
        stmt = (
            select(DimAdsetOrAdgroup.adset_id)
            .where(
                DimAdsetOrAdgroup.campaign_id == campaign_id,
                DimAdsetOrAdgroup.external_adset_id == external_id,
            )
            .limit(1)
        )
        result = await session.execute(stmt)
        existing = result.scalar_one_or_none()
        if existing:
            return existing

    if name:
        stmt = (
            select(DimAdsetOrAdgroup.adset_id)
            .where(
                DimAdsetOrAdgroup.campaign_id == campaign_id,
                DimAdsetOrAdgroup.adset_name == name,
            )
            .limit(1)
        )
        result = await session.execute(stmt)
        existing = result.scalar_one_or_none()
        if existing:
            return existing

    insert_values = {
        "campaign_id": campaign_id,
        "external_adset_id": external_id,
        "adset_name": name,
    }
    result = await session.execute(
        insert(DimAdsetOrAdgroup)
        .values(**insert_values)
        .returning(DimAdsetOrAdgroup.adset_id)
    )
    adset_id = result.scalar_one()
    await session.flush()
    return adset_id


async def ensure_ad_id(
    session: AsyncSession,
    adset_id: int,
    *,
    external_id: str | None = None,
    name: str | None = None,
) -> int:
    """Return the ad identifier for the provided ad set/name pair."""

    if external_id:
        stmt = (
            select(DimAd.ad_id)
            .where(
                DimAd.adset_id == adset_id,
                DimAd.external_ad_id == external_id,
            )
            .limit(1)
        )
        result = await session.execute(stmt)
        existing = result.scalar_one_or_none()
        if existing:
            return existing

    if name:
        stmt = (
            select(DimAd.ad_id)
            .where(
                DimAd.adset_id == adset_id,
                DimAd.ad_name == name,
            )
            .limit(1)
        )
        result = await session.execute(stmt)
        existing = result.scalar_one_or_none()
        if existing:
            return existing

    insert_values = {
        "adset_id": adset_id,
        "external_ad_id": external_id,
        "ad_name": name,
    }
    result = await session.execute(
        insert(DimAd)
        .values(**insert_values)
        .returning(DimAd.ad_id)
    )
    ad_id = result.scalar_one()
    await session.flush()
    return ad_id
