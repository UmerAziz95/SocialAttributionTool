"""Handler for Google spend extracts."""
from __future__ import annotations

from typing import Iterable

from sqlalchemy import delete, insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.marketing import FactMarketingDaily
from app.services.ingestion.base import IngestionHandler
from app.services.ingestion.dimensions import (
    DimensionResolver,
    ensure_account_id,
    ensure_ad_id,
    ensure_adset_id,
    ensure_campaign_id,
    ensure_date_id,
    ensure_platform_id,
)
from app.services.ingestion.logging import log_event
from app.services.ingestion.parsers import parse_date, parse_decimal, parse_int
from app.services.ingestion.types import IngestionContext, IngestionResult
from app.services.ingestion.utils import NormalizationResult


class GoogleSpendHandler(IngestionHandler):
    file_patterns = ("google",)
    required_columns: Iterable[str] = (
        "day",
        "campaign",
        "currency_code",
        "cost",
    )

    def matches(self, file_path: str) -> bool:  # type: ignore[override]
        return any(pattern in file_path.lower() for pattern in self.file_patterns)

    async def validate(
        self, normalized: NormalizationResult, context: IngestionContext
    ) -> None:  # type: ignore[override]
        self._ensure_required_columns(normalized, self.required_columns)
        for key in ("platform_id", "account_id"):
            if key not in context.column_map:
                raise ValueError(f"column_map must include '{key}' for Google ingestions")

    async def ingest(
        self,
        session: AsyncSession,
        normalized: NormalizationResult,
        context: IngestionContext,
    ) -> IngestionResult:  # type: ignore[override]
        resolver = DimensionResolver(context.column_map)
        result = IngestionResult()

        platform_id = resolver.require("platform_id")
        account_id = resolver.require("account_id")
        platform_name = resolver.optional("platform_name") or resolver.optional(
            "platform_label"
        )
        ensured_platform_id = await ensure_platform_id(
            session,
            platform_id,
            name=platform_name,
        )

        log_event(
            "PLATFORM_DIMENSION_ENSURED",
            handler=self.__class__.__name__,
            supplied_platform_id=platform_id,
            ensured_platform_id=ensured_platform_id,
            platform_name=platform_name,
        )

        platform_id = ensured_platform_id

        account_external_id = resolver.optional("account_external_id")
        account_name = resolver.optional("account_name") or resolver.optional(
            "account_label"
        )
        ensured_account_id = await ensure_account_id(
            session,
            account_id,
            platform_id,
            external_id=account_external_id,
            name=account_name,
        )

        log_event(
            "ACCOUNT_DIMENSION_ENSURED",
            handler=self.__class__.__name__,
            supplied_account_id=account_id,
            ensured_account_id=ensured_account_id,
            platform_id=platform_id,
            account_external_id=account_external_id,
            account_name=account_name,
        )

        account_id = ensured_account_id
        default_campaign_name = "Google Campaign"
        default_adset_name = "Google Ad Set"
        default_ad_name = "Google Ad"
        attribution_id = await self._resolve_attribution_id(session, context)
        if not attribution_id:
            attribution_id = resolver.optional("attribution_id")

        currency_code = context.currency_code or resolver.optional("currency_code")

        log_event(
            "HANDLER_CONTEXT_RESOLVED",
            handler=self.__class__.__name__,
            platform_id=platform_id,
            account_id=account_id,
            campaign_id=resolver.optional("campaign_id"),
            adset_id=resolver.optional("adset_id"),
            ad_id=resolver.optional("ad_id"),
            attribution_id=attribution_id,
            currency_code=currency_code,
        )

        payload: list[dict] = []
        delete_scopes: set[tuple[int, int, int, int]] = set()

        for index, row in enumerate(normalized.rows, start=1):
            values = row.values
            day_raw = values.get("day", "")
            maybe_date = parse_date(day_raw)
            if not maybe_date:
                result.warnings.append(
                    f"Row {index}: invalid or missing date '{day_raw}'"
                )
                result.skipped += 1
                log_event(
                    "GOOGLE_ROW_SKIPPED_BAD_DATE",
                    handler=self.__class__.__name__,
                    row_index=index,
                    raw_date=day_raw,
                )
                continue

            date_id = await ensure_date_id(session, maybe_date)
            spend = parse_decimal(values.get("cost", ""))
            if spend is None:
                result.warnings.append(
                    f"Row {index}: missing spend in 'cost' column"
                )
                result.skipped += 1
                log_event(
                    "GOOGLE_ROW_SKIPPED_NO_SPEND",
                    handler=self.__class__.__name__,
                    row_index=index,
                )
                continue

            region_label = values.get("region_matched", "")
            dma_label = values.get("dma_region_matched", "")
            country_label = values.get("countryterritory_matched", "")
            adset_name = values.get("ad_group") or values.get("adset")
            ad_name = values.get("ad")

            campaign_id = resolver.optional("campaign_id")
            if campaign_id is None:
                campaign_name = values.get("campaign") or default_campaign_name
                campaign_id = await ensure_campaign_id(
                    session, account_id, name=campaign_name
                )

            adset_id = resolver.optional("adset_id")
            if adset_id is None:
                adset_id = await ensure_adset_id(
                    session,
                    campaign_id,
                    name=adset_name or values.get("campaign") or default_adset_name,
                )

            ad_id = resolver.optional("ad_id")
            if ad_id is None:
                ad_id = await ensure_ad_id(
                    session,
                    adset_id,
                    name=ad_name
                    or adset_name
                    or values.get("campaign")
                    or default_ad_name,
                )

            payload.append(
                {
                    "platform_id": platform_id,
                    "account_id": account_id,
                    "campaign_id": campaign_id,
                    "adset_id": adset_id,
                    "ad_id": ad_id,
                    "date_id": date_id,
                    "region_id": resolver.resolve_mapping("region_map", region_label),
                    "dma_id": resolver.resolve_mapping("dma_map", dma_label),
                    "country_id": resolver.resolve_mapping("country_map", country_label),
                    "attribution_id": attribution_id,
                    "currency_code": currency_code or values.get("currency_code", ""),
                    "spend": spend,
                    "impressions": parse_int(values.get("impr", "")),
                    "clicks": parse_int(values.get("clicks", "")),
                    "conversions": parse_int(values.get("conversions", "")),
                    "conversion_value": parse_decimal(values.get("conv_value", "")),
                }
            )
            delete_scopes.add((campaign_id, adset_id, ad_id, date_id))
            log_event(
                "GOOGLE_ROW_READY",
                handler=self.__class__.__name__,
                row_index=index,
                date_id=date_id,
                region_label=region_label,
                dma_label=dma_label,
                country_label=country_label,
                spend=spend,
            )

        log_event(
            "PAYLOAD_PREPARED",
            handler=self.__class__.__name__,
            rows_prepared=len(payload),
            rows_skipped=result.skipped,
            warnings_count=len(result.warnings),
            sample_row=payload[0] if payload else None,
        )

        if context.dry_run or not payload:
            log_event(
                "DRY_RUN_SUMMARY" if context.dry_run else "NO_DATA_SUMMARY",
                handler=self.__class__.__name__,
                rows_considered=len(normalized.rows),
                payload_rows=len(payload),
                skipped=result.skipped,
                warnings=result.warnings,
            )
            result.inserted = len(payload)
            if context.dry_run:
                result.summary = (
                    f"Dry run prepared {len(payload)} Google spend rows for fact_marketing_daily; "
                    f"skipped {result.skipped}."
                )
            else:
                result.summary = (
                    "No Google spend rows were written; add date headers or mappings and retry."
                )
            return result

        date_ids = {item["date_id"] for item in payload}
        log_event(
            "DATABASE_WRITE_BEGIN",
            handler=self.__class__.__name__,
            payload_rows=len(payload),
            unique_dates=len(date_ids),
        )
        log_event(
            "DATABASE_DELETE_SCOPE",
            handler=self.__class__.__name__,
            scopes=[
                {
                    "campaign_id": c,
                    "adset_id": a,
                    "ad_id": ad,
                    "date_id": d,
                }
                for c, a, ad, d in sorted(delete_scopes)
            ],
        )
        for scope_campaign_id, scope_adset_id, scope_ad_id, scope_date_id in sorted(
            delete_scopes
        ):
            delete_stmt = delete(FactMarketingDaily).where(
                FactMarketingDaily.platform_id == platform_id,
                FactMarketingDaily.account_id == account_id,
                FactMarketingDaily.campaign_id == scope_campaign_id,
                FactMarketingDaily.adset_id == scope_adset_id,
                FactMarketingDaily.ad_id == scope_ad_id,
                FactMarketingDaily.date_id == scope_date_id,
            )
            await session.execute(delete_stmt)
        await session.execute(insert(FactMarketingDaily), payload)
        await session.commit()

        log_event(
            "DATABASE_WRITE_COMPLETE",
            handler=self.__class__.__name__,
            inserted=len(payload),
            skipped=result.skipped,
            warnings=result.warnings,
        )

        result.inserted = len(payload)
        result.summary = (
            f"Inserted {len(payload)} Google spend rows into fact_marketing_daily; skipped {result.skipped}."
        )
        return result
