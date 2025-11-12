"""Ingestion handlers for marketing data landing in fact_marketing_daily."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable

from sqlalchemy import delete, insert, or_
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
    ensure_dma_id,
    ensure_platform_id,
)
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
    dma_null_tokens: tuple[str, ...] = (
        "unknown",
        "not reported",
        "not set",
        "not available",
        "n/a",
        "na",
        "-",
        "--",
    )
    campaign_name_fields: tuple[str, ...] = ("campaign_name",)
    campaign_external_id_fields: tuple[str, ...] = ("campaign_id", "external_campaign_id")
    adset_name_fields: tuple[str, ...] = ("adset_name", "ad_group_name")
    adset_external_id_fields: tuple[str, ...] = (
        "adset_id",
        "ad_group_id",
        "external_adset_id",
    )
    ad_name_fields: tuple[str, ...] = ("ad_name",)
    ad_external_id_fields: tuple[str, ...] = ("ad_id", "external_ad_id")

    def matches(self, file_path: str) -> bool:  # type: ignore[override]
        lowered = file_path.lower()
        return any(pattern in lowered for pattern in self.file_patterns)

    async def validate(
        self, normalized: NormalizationResult, context: IngestionContext
    ) -> None:  # type: ignore[override]
        self._ensure_required_columns(normalized, self.required_columns)
        for key in ("platform_id", "account_id"):
            if key not in context.column_map:
                raise ValueError(f"column_map must include '{key}' for marketing ingestions")

        self._ensure_dimension_inputs(
            normalized,
            context,
            direct_key="campaign_id",
            map_key="campaign_map",
            candidates=self.campaign_name_fields + self.campaign_external_id_fields,
            label="campaign",
        )
        self._ensure_dimension_inputs(
            normalized,
            context,
            direct_key="adset_id",
            map_key="adset_map",
            candidates=self.adset_name_fields + self.adset_external_id_fields,
            label="ad set/ad group",
        )
        self._ensure_dimension_inputs(
            normalized,
            context,
            direct_key="ad_id",
            map_key="ad_map",
            candidates=self.ad_name_fields + self.ad_external_id_fields,
            label="ad",
        )

    async def ingest(
        self,
        session: AsyncSession,
        normalized: NormalizationResult,
        context: IngestionContext,
    ) -> IngestionResult:  # type: ignore[override]
        resolver = DimensionResolver(context.column_map)
        result = IngestionResult()

        platform_id = self._coerce_int(resolver.require("platform_id"), "platform_id")
        account_id = self._coerce_int(resolver.require("account_id"), "account_id")

        platform_name = resolver.optional("platform_name") or resolver.optional("platform_label")
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
        account_name = resolver.optional("account_name") or resolver.optional("account_label")
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
        attribution_id = await self._resolve_attribution_id(session, context)
        if not attribution_id:
            attribution_id = resolver.optional("attribution_id")

        currency_code = context.currency_code or resolver.optional("currency_code")

        log_event(
            "HANDLER_CONTEXT_RESOLVED",
            handler=self.__class__.__name__,
            platform_id=platform_id,
            account_id=account_id,
            attribution_id=attribution_id,
            currency_code=currency_code,
        )

        payload: list[dict] = []
        warnings: list[str] = []

        dma_ids: set[int] = set()
        include_null_dma = False
        region_ids: set[int] = set()
        include_null_region = False
        date_ids: set[int] = set()
        campaign_ids: set[int] = set()
        adset_ids: set[int] = set()
        ad_ids: set[int] = set()
        campaign_cache: dict[tuple[int, str, str], int] = {}
        adset_cache: dict[tuple[int, str, str], int] = {}
        ad_cache: dict[tuple[int, str, str], int] = {}

        skipped_rows = 0

        for index, row in enumerate(normalized.rows, start=1):
            values = row.values
            raw_date = values.get(self.date_column, "") or ""
            parsed_date = parse_date(raw_date)
            if not parsed_date:
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
                skipped_rows += 1
                continue

            date_id = await ensure_date_id(session, parsed_date)
            log_event(
                "ROW_DATE_RESOLVED",
                handler=self.__class__.__name__,
                row_index=index,
                date=str(parsed_date),
                date_id=date_id,
            )

            campaign_id = await self._resolve_campaign_id(
                session,
                resolver,
                account_id,
                values,
                campaign_cache,
                index,
                warnings,
                context,
            )
            if campaign_id is None:
                skipped_rows += 1
                continue

            adset_id = await self._resolve_adset_id(
                session,
                resolver,
                campaign_id,
                values,
                adset_cache,
                index,
                warnings,
                context,
            )
            if adset_id is None:
                skipped_rows += 1
                continue

            ad_id = await self._resolve_ad_id(
                session,
                resolver,
                adset_id,
                values,
                ad_cache,
                index,
                warnings,
                context,
            )
            if ad_id is None:
                skipped_rows += 1
                continue

            dma_id = None
            raw_dma = ""
            dma_placeholder = False
            if self.dma_column:
                raw_dma = values.get(self.dma_column, "") or ""
                if raw_dma:
                    if self._should_treat_dma_as_null(raw_dma):
                        include_null_dma = True
                        dma_placeholder = True
                        log_event(
                            "ROW_DMA_TREATED_AS_NULL",
                            handler=self.__class__.__name__,
                            row_index=index,
                            raw_value=raw_dma,
                        )
                    else:
                        dma_id = resolver.resolve_mapping("dma_map", raw_dma)
                        if dma_id is not None:
                            dma_id = self._coerce_int(dma_id, "dma_id")
                            log_event(
                                "ROW_DMA_RESOLVED_MAPPING",
                                handler=self.__class__.__name__,
                                row_index=index,
                                raw_value=raw_dma,
                                dma_id=dma_id,
                            )
                        else:
                            dma_id = await ensure_dma_id(
                                session,
                                platform_id,
                                label=raw_dma,
                            )
                            if dma_id is not None:
                                log_event(
                                    "ROW_DMA_AUTO_MAPPED",
                                    handler=self.__class__.__name__,
                                    row_index=index,
                                    raw_value=raw_dma,
                                    dma_id=dma_id,
                                )
                        if dma_id is None:
                            include_null_dma = True
                            if not dma_placeholder:
                                warnings.append(
                                    f"Row {index}: unknown DMA '{raw_dma}' — add a column_map.dma_map entry or supply dma_map overrides"
                                )
                                log_event(
                                    "ROW_DMA_UNRESOLVED",
                                    handler=self.__class__.__name__,
                                    row_index=index,
                                    raw_value=raw_dma,
                                )
                                if context.fail_fast:
                                    raise ValueError(f"Unable to resolve DMA '{raw_dma}'")

            region_id = None
            if self.region_column:
                raw_region = values.get(self.region_column, "") or ""
                region_id = resolver.resolve_mapping("region_map", raw_region)
                if raw_region and region_id is None:
                    warnings.append(
                        f"Row {index}: unknown region '{raw_region}' — add a column_map.region_map entry"
                    )
                    log_event(
                        "ROW_REGION_UNRESOLVED",
                        handler=self.__class__.__name__,
                        row_index=index,
                        raw_value=raw_region,
                    )
                    if context.fail_fast:
                        raise ValueError(f"Unable to resolve region '{raw_region}'")
                    region_id = None

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
            if dma_id is not None:
                dma_ids.add(dma_id)
            elif self.dma_column:
                include_null_dma = True
            if region_id is not None:
                region_ids.add(region_id)
            else:
                include_null_region = include_null_region or bool(self.region_column)
            campaign_ids.add(campaign_id)
            adset_ids.add(adset_id)
            ad_ids.add(ad_id)
            log_event(
                "ROW_READY",
                handler=self.__class__.__name__,
                row_index=index,
                date_id=date_id,
                dma_id=dma_id,
                region_id=region_id,
                metrics=metrics,
            )

        result.skipped = skipped_rows
        result.warnings.extend(warnings)

        log_event(
            "PAYLOAD_PREPARED",
            handler=self.__class__.__name__,
            rows_prepared=len(payload),
            rows_skipped=skipped_rows,
            warnings_count=len(warnings),
            sample_row=payload[0] if payload else None,
        )

        if context.dry_run or not payload:
            log_event(
                "DRY_RUN_SUMMARY" if context.dry_run else "NO_DATA_SUMMARY",
                handler=self.__class__.__name__,
                rows_considered=len(normalized.rows),
                payload_rows=len(payload),
                skipped=skipped_rows,
                warnings=warnings,
            )
            result.inserted = len(payload)
            if context.dry_run:
                result.summary = (
                    f"Dry run prepared {len(payload)} marketing rows for fact_marketing_daily; "
                    f"skipped {skipped_rows}."
                )
            else:
                result.summary = (
                    "No marketing rows were written; provide dimension mappings to enable ingestion."
                )
            return result

        delete_conditions = [
            FactMarketingDaily.platform_id == platform_id,
            FactMarketingDaily.account_id == account_id,
            FactMarketingDaily.date_id.in_(date_ids),
        ]
        if campaign_ids:
            delete_conditions.append(FactMarketingDaily.campaign_id.in_(campaign_ids))
        if adset_ids:
            delete_conditions.append(FactMarketingDaily.adset_id.in_(adset_ids))
        if ad_ids:
            delete_conditions.append(FactMarketingDaily.ad_id.in_(ad_ids))

        delete_stmt = delete(FactMarketingDaily).where(*delete_conditions)
        if self.dma_column and (dma_ids or include_null_dma):
            dma_filters: list = []
            if dma_ids:
                dma_filters.append(FactMarketingDaily.dma_id.in_(dma_ids))
            if include_null_dma:
                dma_filters.append(FactMarketingDaily.dma_id.is_(None))
            if dma_filters:
                delete_stmt = delete_stmt.where(
                    or_(*dma_filters) if len(dma_filters) > 1 else dma_filters[0]
                )
        if self.region_column and (region_ids or include_null_region):
            region_filters: list = []
            if region_ids:
                region_filters.append(FactMarketingDaily.region_id.in_(region_ids))
            if include_null_region:
                region_filters.append(FactMarketingDaily.region_id.is_(None))
            if region_filters:
                delete_stmt = delete_stmt.where(
                    or_(*region_filters) if len(region_filters) > 1 else region_filters[0]
                )

        log_event(
            "DATABASE_WRITE_BEGIN",
            handler=self.__class__.__name__,
            payload_rows=len(payload),
            unique_dates=len(date_ids),
            unique_dmas=len(dma_ids),
            includes_null_dma=include_null_dma,
            unique_regions=len(region_ids),
            includes_null_region=include_null_region,
        )
        log_event(
            "DATABASE_DELETE_SCOPE",
            handler=self.__class__.__name__,
            date_ids=sorted(date_ids),
            dma_ids=sorted(dma_ids),
            include_null_dma=include_null_dma,
            region_ids=sorted(region_ids),
            include_null_region=include_null_region,
        )
        await session.execute(delete_stmt)
        if payload:
            await session.execute(insert(FactMarketingDaily), payload)
        await session.commit()

        log_event(
            "DATABASE_WRITE_COMPLETE",
            handler=self.__class__.__name__,
            inserted=len(payload),
            skipped=skipped_rows,
            warnings=warnings,
        )

        result.inserted = len(payload)
        result.summary = (
            f"Inserted {len(payload)} marketing rows into fact_marketing_daily; skipped {skipped_rows}."
        )
        return result

    def _should_treat_dma_as_null(self, raw_value: str) -> bool:
        normalized = " ".join(raw_value.strip().lower().split())
        if not normalized:
            return True
        if normalized in self.dma_null_tokens:
            return True
        return normalized.startswith("unknown ")

    def _ensure_dimension_inputs(
        self,
        normalized: NormalizationResult,
        context: IngestionContext,
        *,
        direct_key: str,
        map_key: str,
        candidates: Iterable[str],
        label: str,
    ) -> None:
        if direct_key in context.column_map or map_key in context.column_map:
            return
        if any(column in normalized.headers for column in candidates):
            return
        readable = ", ".join(sorted(candidates))
        raise ValueError(
            f"Provide column_map.{direct_key} or include one of [{readable}] columns to resolve the {label}."
        )

    def _coerce_int(self, value: object, label: str) -> int:
        try:
            return int(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):  # pragma: no cover - defensive guard
            raise ValueError(f"{label} must be an integer, received {value!r}")

    def _first_non_empty(self, values: dict[str, str], candidates: Iterable[str]) -> str | None:
        for candidate in candidates:
            raw = values.get(candidate)
            if raw and raw.strip():
                return raw.strip()
        return None

    def _candidate_values(self, values: dict[str, str], candidates: Iterable[str]) -> list[str]:
        collected: list[str] = []
        for candidate in candidates:
            raw = values.get(candidate)
            if raw and raw.strip():
                collected.append(raw.strip())
        return collected

    def _normalized_key(self, *parts: str | None) -> str:
        normalized = "|".join((part or "").strip().lower() for part in parts)
        return normalized

    async def _resolve_campaign_id(
        self,
        session: AsyncSession,
        resolver: DimensionResolver,
        account_id: int,
        values: dict[str, str],
        cache: dict[tuple[int, str, str], int],
        row_index: int,
        warnings: list[str],
        context: IngestionContext,
    ) -> int | None:
        if "campaign_id" in resolver.column_map:
            campaign_id = self._coerce_int(resolver.require("campaign_id"), "campaign_id")
            log_event(
                "ROW_CAMPAIGN_RESOLVED_COLUMN_MAP",
                handler=self.__class__.__name__,
                row_index=row_index,
                campaign_id=campaign_id,
            )
            return campaign_id

        for candidate in self._candidate_values(
            values, self.campaign_name_fields + self.campaign_external_id_fields
        ):
            mapped = resolver.resolve_mapping("campaign_map", candidate)
            if mapped is not None:
                campaign_id = self._coerce_int(mapped, "campaign_map")
                log_event(
                    "ROW_CAMPAIGN_RESOLVED_MAPPING",
                    handler=self.__class__.__name__,
                    row_index=row_index,
                    campaign_id=campaign_id,
                    source_value=candidate,
                )
                return campaign_id

        campaign_name = self._first_non_empty(values, self.campaign_name_fields)
        campaign_external_id = self._first_non_empty(values, self.campaign_external_id_fields)
        cache_key = (account_id, self._normalized_key(campaign_external_id), self._normalized_key(campaign_name))

        if cache_key[1] == "" and cache_key[2] == "":
            warning = (
                f"Row {row_index}: unable to determine campaign from the file — provide column_map.campaign_map "
                "or include campaign columns."
            )
            warnings.append(warning)
            log_event(
                "ROW_SKIPPED_CAMPAIGN_UNRESOLVED",
                handler=self.__class__.__name__,
                row_index=row_index,
                raw=values,
            )
            if context.fail_fast:
                raise ValueError("Unable to resolve campaign for row")
            return None

        if cache_key in cache:
            return cache[cache_key]

        campaign_id = await ensure_campaign_id(
            session,
            account_id,
            external_id=campaign_external_id,
            name=campaign_name,
        )
        cache[cache_key] = campaign_id
        log_event(
            "ROW_CAMPAIGN_RESOLVED",
            handler=self.__class__.__name__,
            row_index=row_index,
            campaign_id=campaign_id,
            campaign_name=campaign_name,
            external_campaign_id=campaign_external_id,
        )
        return campaign_id

    async def _resolve_adset_id(
        self,
        session: AsyncSession,
        resolver: DimensionResolver,
        campaign_id: int,
        values: dict[str, str],
        cache: dict[tuple[int, str, str], int],
        row_index: int,
        warnings: list[str],
        context: IngestionContext,
    ) -> int | None:
        if "adset_id" in resolver.column_map:
            adset_id = self._coerce_int(resolver.require("adset_id"), "adset_id")
            log_event(
                "ROW_ADSET_RESOLVED_COLUMN_MAP",
                handler=self.__class__.__name__,
                row_index=row_index,
                adset_id=adset_id,
            )
            return adset_id

        for candidate in self._candidate_values(
            values, self.adset_name_fields + self.adset_external_id_fields
        ):
            mapped = resolver.resolve_mapping("adset_map", candidate)
            if mapped is not None:
                adset_id = self._coerce_int(mapped, "adset_map")
                log_event(
                    "ROW_ADSET_RESOLVED_MAPPING",
                    handler=self.__class__.__name__,
                    row_index=row_index,
                    adset_id=adset_id,
                    source_value=candidate,
                )
                return adset_id

        adset_name = self._first_non_empty(values, self.adset_name_fields)
        adset_external_id = self._first_non_empty(values, self.adset_external_id_fields)
        cache_key = (campaign_id, self._normalized_key(adset_external_id), self._normalized_key(adset_name))

        if cache_key[1] == "" and cache_key[2] == "":
            warning = (
                f"Row {row_index}: unable to determine ad set/ad group — provide column_map.adset_map "
                "or ensure ad set columns exist."
            )
            warnings.append(warning)
            log_event(
                "ROW_SKIPPED_ADSET_UNRESOLVED",
                handler=self.__class__.__name__,
                row_index=row_index,
                raw=values,
            )
            if context.fail_fast:
                raise ValueError("Unable to resolve ad set for row")
            return None

        if cache_key in cache:
            return cache[cache_key]

        adset_id = await ensure_adset_id(
            session,
            campaign_id,
            external_id=adset_external_id,
            name=adset_name,
        )
        cache[cache_key] = adset_id
        log_event(
            "ROW_ADSET_RESOLVED",
            handler=self.__class__.__name__,
            row_index=row_index,
            adset_id=adset_id,
            adset_name=adset_name,
            external_adset_id=adset_external_id,
        )
        return adset_id

    async def _resolve_ad_id(
        self,
        session: AsyncSession,
        resolver: DimensionResolver,
        adset_id: int,
        values: dict[str, str],
        cache: dict[tuple[int, str, str], int],
        row_index: int,
        warnings: list[str],
        context: IngestionContext,
    ) -> int | None:
        if "ad_id" in resolver.column_map:
            ad_id = self._coerce_int(resolver.require("ad_id"), "ad_id")
            log_event(
                "ROW_AD_RESOLVED_COLUMN_MAP",
                handler=self.__class__.__name__,
                row_index=row_index,
                ad_id=ad_id,
            )
            return ad_id

        for candidate in self._candidate_values(values, self.ad_name_fields + self.ad_external_id_fields):
            mapped = resolver.resolve_mapping("ad_map", candidate)
            if mapped is not None:
                ad_id = self._coerce_int(mapped, "ad_map")
                log_event(
                    "ROW_AD_RESOLVED_MAPPING",
                    handler=self.__class__.__name__,
                    row_index=row_index,
                    ad_id=ad_id,
                    source_value=candidate,
                )
                return ad_id

        ad_name = self._first_non_empty(values, self.ad_name_fields)
        ad_external_id = self._first_non_empty(values, self.ad_external_id_fields)
        cache_key = (adset_id, self._normalized_key(ad_external_id), self._normalized_key(ad_name))

        if cache_key[1] == "" and cache_key[2] == "":
            warning = (
                f"Row {row_index}: unable to determine ad — provide column_map.ad_map or ensure ad columns exist."
            )
            warnings.append(warning)
            log_event(
                "ROW_SKIPPED_AD_UNRESOLVED",
                handler=self.__class__.__name__,
                row_index=row_index,
                raw=values,
            )
            if context.fail_fast:
                raise ValueError("Unable to resolve ad for row")
            return None

        if cache_key in cache:
            return cache[cache_key]

        ad_id = await ensure_ad_id(
            session,
            adset_id,
            external_id=ad_external_id,
            name=ad_name,
        )
        cache[cache_key] = ad_id
        log_event(
            "ROW_AD_RESOLVED",
            handler=self.__class__.__name__,
            row_index=row_index,
            ad_id=ad_id,
            ad_name=ad_name,
            external_ad_id=ad_external_id,
        )
        return ad_id

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
