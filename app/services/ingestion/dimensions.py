"""Helpers for resolving dimension identifiers used during ingestion."""
from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.marketing import DimAd, DimAdsetOrAdgroup, DimCampaign, DimDate


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
