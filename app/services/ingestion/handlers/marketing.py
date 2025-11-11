"""Ingestion handlers for marketing data landing in fact_marketing_daily."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable

from sqlalchemy import delete, insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.marketing import FactMarketingDaily
from app.services.ingestion.base import IngestionHandler
from app.services.ingestion.dimensions import DimensionResolver, ensure_date_id
from app.services.ingestion.logging import log_event
from app.services.ingestion.parsers import parse_date, parse_decimal, parse_int
from app.services.ingestion.types import IngestionContext, IngestionResult
from app.services.ingestion.utils import NormalizationResult


@dataclass(slots=True)
class MetricSpec:
    column: str
    parser: Callable[[str], object]


class MarketingHandler(IngestionHandler):
    file_patterns: tuple[str, ...] = ()
    required_columns: Iterable[str] = ()
    date_column: str = "day"
    dma_column: str | None = None
    region_column: str | None = None
    metric_specs: dict[str, MetricSpec] = {}

    def matches(self, file_path: str) -> bool:  # type: ignore[override]
        lowered = file_path.lower()
        return any(pattern in lowered for pattern in self.file_patterns)

    async def validate(
        self, normalized: NormalizationResult, context: IngestionContext
    ) -> None:  # type: ignore[override]
        self._ensure_required_columns(normalized, self.required_columns)
        for key in ("platform_id", "account_id", "campaign_id", "adset_id", "ad_id"):
            if key not in context.column_map:
                raise ValueError(f"column_map must include '{key}' for marketing ingestions")

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
        campaign_id = resolver.require("campaign_id")
        adset_id = resolver.require("adset_id")
        ad_id = resolver.require("ad_id")
        attribution_id = await self._resolve_attribution_id(session, context)
        if not attribution_id:
            attribution_id = resolver.optional("attribution_id")

        currency_code = context.currency_code or resolver.optional("currency_code")

        log_event(
            "HANDLER_CONTEXT_RESOLVED",
            handler=self.__class__.__name__,
            platform_id=platform_id,
            account_id=account_id,
            campaign_id=campaign_id,
            adset_id=adset_id,
            ad_id=ad_id,
            attribution_id=attribution_id,
            currency_code=currency_code,
        )

        payload: list[dict] = []
        skipped = 0
        warnings: list[str] = []

        dma_ids: set[int | None] = set()
        region_ids: set[int | None] = set()
        date_ids: set[int] = set()

        for index, row in enumerate(normalized.rows, start=1):
            values = row.values
            raw_date = values.get(self.date_column, "") or ""
            parsed_date = parse_date(raw_date)
            if not parsed_date:
                skipped += 1
                warnings.append(
                    f"Row {index}: invalid date value '{raw_date}' — provide a parsable date"
                )
                log_event(
                    "ROW_SKIPPED_INVALID_DATE",
                    handler=self.__class__.__name__,
                    row_index=index,
                    raw=values,
                )
                if context.fail_fast:
                    raise ValueError("Encountered row without valid date")
                continue

            date_id = await ensure_date_id(session, parsed_date)
            log_event(
                "ROW_DATE_RESOLVED",
                handler=self.__class__.__name__,
                row_index=index,
                date=str(parsed_date),
                date_id=date_id,
            )

            dma_id = None
            if self.dma_column:
                raw_dma = values.get(self.dma_column, "") or ""
                dma_id = resolver.resolve_mapping("dma_map", raw_dma)
                if raw_dma and dma_id is None:
                    warnings.append(
                        f"Row {index}: unknown DMA '{raw_dma}' — add a column_map.dma_map entry"
                    )
                    log_event(
                        "ROW_SKIPPED_UNKNOWN_DMA",
                        handler=self.__class__.__name__,
                        row_index=index,
                        raw_value=raw_dma,
                    )
                    if context.fail_fast:
                        raise ValueError(f"Unable to resolve DMA '{raw_dma}'")
                    skipped += 1
                    continue

            region_id = None
            if self.region_column:
                raw_region = values.get(self.region_column, "") or ""
                region_id = resolver.resolve_mapping("region_map", raw_region)
                if raw_region and region_id is None:
                    warnings.append(
                        f"Row {index}: unknown region '{raw_region}' — add a column_map.region_map entry"
                    )
                    log_event(
                        "ROW_SKIPPED_UNKNOWN_REGION",
                        handler=self.__class__.__name__,
                        row_index=index,
                        raw_value=raw_region,
                    )
                    if context.fail_fast:
                        raise ValueError(f"Unable to resolve region '{raw_region}'")
                    skipped += 1
                    continue

            metrics: dict[str, object] = {}
            for target_column, spec in self.metric_specs.items():
                parsed_value = spec.parser(values.get(spec.column, ""))
                metrics[target_column] = parsed_value

            payload.append(
                {
                    "platform_id": platform_id,
                    "account_id": account_id,
                    "campaign_id": campaign_id,
                    "adset_id": adset_id,
                    "ad_id": ad_id,
                    "date_id": date_id,
                    "attribution_id": attribution_id,
                    "dma_id": dma_id,
                    "region_id": region_id,
                    "currency_code": currency_code,
                    **metrics,
                }
            )
            date_ids.add(date_id)
            dma_ids.add(dma_id)
            region_ids.add(region_id)
            log_event(
                "ROW_READY",
                handler=self.__class__.__name__,
                row_index=index,
                date_id=date_id,
                dma_id=dma_id,
                region_id=region_id,
                metrics=metrics,
            )

        result.skipped = skipped
        result.warnings.extend(warnings)

        log_event(
            "PAYLOAD_PREPARED",
            handler=self.__class__.__name__,
            rows_prepared=len(payload),
            rows_skipped=skipped,
            warnings_count=len(warnings),
            sample_row=payload[0] if payload else None,
        )

        if context.dry_run or not payload:
            log_event(
                "DRY_RUN_SUMMARY" if context.dry_run else "NO_DATA_SUMMARY",
                handler=self.__class__.__name__,
                rows_considered=len(normalized.rows),
                payload_rows=len(payload),
                skipped=skipped,
                warnings=warnings,
            )
            result.inserted = len(payload)
            if context.dry_run:
                result.summary = (
                    f"Dry run prepared {len(payload)} marketing rows for fact_marketing_daily; "
                    f"skipped {skipped}."
                )
            else:
                result.summary = (
                    "No marketing rows were written; provide dimension mappings to enable ingestion."
                )
            return result

        delete_stmt = delete(FactMarketingDaily).where(
            FactMarketingDaily.platform_id == platform_id,
            FactMarketingDaily.account_id == account_id,
            FactMarketingDaily.campaign_id == campaign_id,
            FactMarketingDaily.adset_id == adset_id,
            FactMarketingDaily.ad_id == ad_id,
            FactMarketingDaily.date_id.in_(date_ids),
        )
        if self.dma_column:
            delete_stmt = delete_stmt.where(FactMarketingDaily.dma_id.in_(dma_ids))
        if self.region_column:
            delete_stmt = delete_stmt.where(FactMarketingDaily.region_id.in_(region_ids))

        log_event(
            "DATABASE_WRITE_BEGIN",
            handler=self.__class__.__name__,
            payload_rows=len(payload),
            unique_dates=len(date_ids),
            unique_dmas=len([item for item in dma_ids if item is not None]),
            unique_regions=len([item for item in region_ids if item is not None]),
        )
        log_event(
            "DATABASE_DELETE_SCOPE",
            handler=self.__class__.__name__,
            date_ids=sorted(date_ids),
            dma_ids=[item for item in dma_ids if item is not None],
            region_ids=[item for item in region_ids if item is not None],
        )
        await session.execute(delete_stmt)
        if payload:
            await session.execute(insert(FactMarketingDaily), payload)
        await session.commit()

        log_event(
            "DATABASE_WRITE_COMPLETE",
            handler=self.__class__.__name__,
            inserted=len(payload),
            skipped=skipped,
            warnings=warnings,
        )

        result.inserted = len(payload)
        result.summary = (
            f"Inserted {len(payload)} marketing rows into fact_marketing_daily; skipped {skipped}."
        )
        return result

class MetaDMAHandler(MarketingHandler):
    file_patterns = ("dma_performance_meta",)
    required_columns = (
        "dma_region",
        "day",
        "impressions",
        "amount_spent_aud",
    )
    dma_column = "dma_region"
    metric_specs = {
        "spend": MetricSpec("amount_spent_aud", parse_decimal),
        "impressions": MetricSpec("impressions", parse_int),
        "clicks": MetricSpec("link_clicks", parse_int),
        "reach": MetricSpec("reach", parse_int),
        "frequency": MetricSpec("frequency", parse_decimal),
        "add_to_cart": MetricSpec("adds_to_cart", parse_int),
    }


class MetaRegionHandler(MarketingHandler):
    file_patterns = ("region_performance_meta",)
    required_columns = (
        "region",
        "day",
        "impressions",
        "amount_spent_aud",
    )
    region_column = "region"
    metric_specs = {
        "spend": MetricSpec("amount_spent_aud", parse_decimal),
        "impressions": MetricSpec("impressions", parse_int),
        "clicks": MetricSpec("link_clicks", parse_int),
        "reach": MetricSpec("reach", parse_int),
        "frequency": MetricSpec("frequency", parse_decimal),
        "add_to_cart": MetricSpec("adds_to_cart", parse_int),
    }


class PinterestDMAHandler(MarketingHandler):
    file_patterns = ("metro+ads_performance_pinterest",)
    required_columns = ("targeting_value", "date", "paid_impressions")
    dma_column = "targeting_value"
    metric_specs = {
        "spend": MetricSpec("spend_in_account_currency", parse_decimal),
        "impressions": MetricSpec("paid_impressions", parse_int),
        "clicks": MetricSpec("paid_pin_clicks", parse_int),
        "conversions": MetricSpec("total_conversions_checkout", parse_int),
        "conversion_value": MetricSpec("total_order_value_checkout", parse_decimal),
        "add_to_cart": MetricSpec("web_conversions_add_to_cart", parse_int),
        "video_view_time": MetricSpec("paid_average_video_play_time", parse_decimal),
    }


class PinterestRegionHandler(MarketingHandler):
    file_patterns = ("region+ads_performance_pinterest",)
    required_columns = ("targeting_value", "date", "paid_impressions")
    region_column = "targeting_value"
    metric_specs = {
        "spend": MetricSpec("spend_in_account_currency", parse_decimal),
        "impressions": MetricSpec("paid_impressions", parse_int),
        "clicks": MetricSpec("paid_pin_clicks", parse_int),
        "conversions": MetricSpec("total_conversions_checkout", parse_int),
        "conversion_value": MetricSpec("total_order_value_checkout", parse_decimal),
        "add_to_cart": MetricSpec("web_conversions_add_to_cart", parse_int),
        "video_view_time": MetricSpec("paid_average_video_play_time", parse_decimal),
    }


class TikTokDMAHandler(MarketingHandler):
    file_patterns = ("tiktok_by_dma",)
    required_columns = ("dma", "by_day", "cost")
    date_column = "by_day"
    dma_column = "dma"
    metric_specs = {
        "spend": MetricSpec("cost", parse_decimal),
        "impressions": MetricSpec("impressions", parse_int),
        "clicks": MetricSpec("clicks_destination", parse_int),
        "conversions": MetricSpec("conversions", parse_int),
        "frequency": MetricSpec("frequency", parse_decimal),
    }


class TikTokRegionHandler(MarketingHandler):
    file_patterns = ("tiktok_by_region",)
    required_columns = ("subregion", "by_day", "cost")
    date_column = "by_day"
    region_column = "subregion"
    metric_specs = {
        "spend": MetricSpec("cost", parse_decimal),
        "impressions": MetricSpec("impressions", parse_int),
        "clicks": MetricSpec("clicks_destination", parse_int),
        "conversions": MetricSpec("conversions", parse_int),
        "frequency": MetricSpec("frequency", parse_decimal),
    }


class TikTokAdsHandler(MarketingHandler):
    file_patterns = ("tiktok_by_ads_freq_addtocart",)
    required_columns = ("by_day", "cost")
    date_column = "by_day"
    metric_specs = {
        "spend": MetricSpec("cost", parse_decimal),
        "impressions": MetricSpec("impressions", parse_int),
        "clicks": MetricSpec("clicks_destination", parse_int),
        "conversions": MetricSpec("conversions", parse_int),
        "frequency": MetricSpec("frequency", parse_decimal),
        "add_to_cart": MetricSpec("adds_to_cart_website", parse_int),
        "conversion_value": MetricSpec("add_to_cart_value_website", parse_decimal),
    }
