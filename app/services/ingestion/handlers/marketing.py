"""Ingestion handlers for marketing data landing in fact_marketing_daily."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Iterable

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.marketing import DimRegion, FactMarketingDaily
from app.services.ingestion.base import IngestionHandler
from app.services.ingestion.dimensions import (
    DimensionResolver,
    ensure_account_id,
    ensure_ad_id,
    ensure_adset_id,
    ensure_campaign_id,
    ensure_date_id,
    ensure_country_id,
    ensure_dma_id,
    ensure_region_id,
    ensure_platform_id,
    standardize_dma_label,
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
    adset_name_fields: tuple[str, ...] = (
        "adset_name",
        "ad_set_name",
        "ad_group_name",
    )
    adset_external_id_fields: tuple[str, ...] = (
        "adset_id",
        "ad_set_id",
        "ad_group_id",
        "external_adset_id",
    )
    ad_name_fields: tuple[str, ...] = ("ad_name",)
    ad_external_id_fields: tuple[str, ...] = ("ad_id", "external_ad_id")
    require_adset_inputs: bool = True
    require_ad_inputs: bool = True

    def _fallback_adset_name(
        self, values: dict[str, str], row_index: int
    ) -> str | None:
        """Hook for subclasses that need to synthesize ad set names."""

        return None

    def _fallback_ad_name(
        self, values: dict[str, str], row_index: int, adset_name: str | None
    ) -> str | None:
        """Hook for subclasses that need to synthesize ad names."""

        return None

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
        if self.require_adset_inputs:
            self._ensure_dimension_inputs(
                normalized,
                context,
                direct_key="adset_id",
                map_key="adset_map",
                candidates=self.adset_name_fields + self.adset_external_id_fields,
                label="ad set/ad group",
            )
        if self.require_ad_inputs:
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

        payload_chunk: list[dict] = []
        total_prepared = 0
        total_written = 0
        batch_size = max(1, context.batch_size)
        # asyncpg limits bind parameters per statement (~32k). Constrain the
        # per-statement batch size once we know how many columns each row
        # carries so we never exceed the driver limit even if callers pass a
        # very large batch_size.
        max_rows_per_statement: int | None = None
        effective_batch_size = batch_size
        first_payload_sample: dict | None = None
        warnings: list[str] = []

        dma_ids: set[int] = set()
        include_null_dma = False
        region_ids: set[int] = set()
        include_null_region = False
        country_ids: set[int] = set()
        include_null_country = False
        date_ids: set[int] = set()
        date_labels: set[str] = set()
        campaign_ids: set[int] = set()
        adset_ids: set[int] = set()
        ad_ids: set[int] = set()
        campaign_cache: dict[tuple[int, str, str], int] = {}
        adset_cache: dict[tuple[int, str, str], int] = {}
        ad_cache: dict[tuple[int, str, str], int] = {}

        skipped_rows = 0

        async def flush_chunk() -> None:
            nonlocal total_written
            if not payload_chunk:
                return

            upsert_stmt = pg_insert(FactMarketingDaily).values(payload_chunk)
            update_fields = {
                "attribution_id": upsert_stmt.excluded.attribution_id,
                "country_id": upsert_stmt.excluded.country_id,
                "region_id": upsert_stmt.excluded.region_id,
                "dma_id": upsert_stmt.excluded.dma_id,
                "currency_code": upsert_stmt.excluded.currency_code,
                "spend": upsert_stmt.excluded.spend,
                "impressions": upsert_stmt.excluded.impressions,
                "clicks": upsert_stmt.excluded.clicks,
                "conversions": upsert_stmt.excluded.conversions,
                "conversion_value": upsert_stmt.excluded.conversion_value,
                "video_view_time": upsert_stmt.excluded.video_view_time,
                "frequency": upsert_stmt.excluded.frequency,
                "reach": upsert_stmt.excluded.reach,
                "add_to_cart": upsert_stmt.excluded.add_to_cart,
            }

            await session.execute(
                upsert_stmt.on_conflict_do_update(
                    constraint="ux_fact_marketing_daily_grain",
                    set_=update_fields,
                )
            )
            await session.commit()

            total_written += len(payload_chunk)
            payload_chunk.clear()

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
            date_labels.add(parsed_date.isoformat())

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
                normalized_dma_label = standardize_dma_label(raw_dma)
                if raw_dma:
                    if self._should_treat_dma_as_null(raw_dma):
                        include_null_dma = True
                        dma_placeholder = True
                        log_event(
                            "ROW_DMA_TREATED_AS_NULL",
                            handler=self.__class__.__name__,
                            row_index=index,
                            raw_value=raw_dma,
                            standardized_value=normalized_dma_label,
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
                                standardized_value=normalized_dma_label,
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
                                    standardized_value=normalized_dma_label,
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
                                    standardized_value=normalized_dma_label,
                                )
                                if context.fail_fast:
                                    raise ValueError(f"Unable to resolve DMA '{raw_dma}'")

            region_id = None
            country_id = None
            if self.region_column:
                raw_region = values.get(self.region_column, "") or ""
                region_id = resolver.resolve_mapping("region_map", raw_region)
                if raw_region:
                    if "country_id" in resolver.column_map:
                        country_id = self._coerce_int(
                            resolver.optional("country_id"), "country_id"
                        )
                    if region_id is None:
                        try:
                            country_id = country_id or await ensure_country_id(session)
                            region_id = await ensure_region_id(
                                session, country_id=country_id, name=raw_region
                            )
                            log_event(
                                "ROW_REGION_CREATED",
                                handler=self.__class__.__name__,
                                row_index=index,
                                region_id=region_id,
                                country_id=country_id,
                                region_name=raw_region,
                            )
                        except Exception:
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
                                raise
                            region_id = None
                            country_id = country_id or None
                    elif country_id is None:
                        existing_region = await session.get(DimRegion, region_id)
                        if existing_region:
                            country_id = existing_region.country_id

            metrics: dict[str, object] = {}
            for target_column, spec in self.metric_specs.items():
                parsed_value = spec.parser(values.get(spec.column, ""))
                metrics[target_column] = parsed_value

            row_payload = {
                "platform_id": platform_id,
                "account_id": account_id,
                "campaign_id": campaign_id,
                "adset_id": adset_id,
                "ad_id": ad_id,
                "date_id": date_id,
                "attribution_id": attribution_id,
                "dma_id": dma_id,
                "country_id": country_id,
                "region_id": region_id,
                "currency_code": currency_code,
                **metrics,
            }

            if first_payload_sample is None:
                first_payload_sample = row_payload

            if max_rows_per_statement is None:
                # Use a conservative ceiling to keep well under the 32k
                # parameter cap: params_per_row * rows_per_statement <= 32000
                params_per_row = max(1, len(row_payload))
                max_rows_per_statement = max(1, 32000 // params_per_row)
                effective_batch_size = min(batch_size, max_rows_per_statement)

            total_prepared += 1
            if not context.dry_run:
                payload_chunk.append(row_payload)
                if len(payload_chunk) >= effective_batch_size:
                    await flush_chunk()
            date_ids.add(date_id)
            if dma_id is not None:
                dma_ids.add(dma_id)
            elif self.dma_column:
                include_null_dma = True
            if region_id is not None:
                region_ids.add(region_id)
            else:
                include_null_region = include_null_region or bool(self.region_column)
            if country_id is not None:
                country_ids.add(country_id)
            else:
                include_null_country = include_null_country or bool(self.region_column)
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
            rows_prepared=total_prepared,
            rows_skipped=skipped_rows,
            warnings_count=len(warnings),
            sample_row=first_payload_sample,
        )

        if context.dry_run or not total_prepared:
            if not total_prepared and not context.dry_run:
                log_event(
                    "MARKETING_NO_ROWS",
                    handler=self.__class__.__name__,
                    file=context.file_path,
                    rows_considered=len(normalized.rows),
                    warnings_count=len(warnings),
                    warnings_sample=warnings[:5],
                )
            log_event(
                "DRY_RUN_SUMMARY" if context.dry_run else "NO_DATA_SUMMARY",
                handler=self.__class__.__name__,
                rows_considered=len(normalized.rows),
                payload_rows=total_prepared,
                skipped=skipped_rows,
                warnings=warnings,
            )
            result.inserted = total_prepared
            result.finished_at = datetime.utcnow()
            result.status = "success"
            if context.dry_run:
                result.summary = (
                    f"Dry run prepared {total_prepared} marketing rows for fact_marketing_daily; "
                    f"skipped {skipped_rows}."
                )
            else:
                result.summary = (
                    "No marketing rows were written; provide dimension mappings to enable ingestion."
                )
            return result

        log_event(
            "DATABASE_WRITE_BEGIN",
            handler=self.__class__.__name__,
            payload_rows=total_prepared,
            unique_dates=len(date_ids),
            unique_dmas=len(dma_ids),
            includes_null_dma=include_null_dma,
            unique_regions=len(region_ids),
            includes_null_region=include_null_region,
            unique_countries=len(country_ids),
            includes_null_country=include_null_country,
        )

        if payload_chunk:
            await flush_chunk()

        if date_labels:
            date_range = (min(date_labels), max(date_labels))
        else:
            date_range = None

        log_event(
            "MARKETING_FACT_SUMMARY",
            handler=self.__class__.__name__,
            file=context.file_path,
            rows_inserted=total_written,
            rows_skipped=skipped_rows,
            platform_id=platform_id,
            account_id=account_id,
            campaigns=len(campaign_ids),
            adsets=len(adset_ids),
            ads=len(ad_ids),
            dma=len(dma_ids),
            regions=len(region_ids),
            countries=len(country_ids),
            date_range=date_range,
            currency_code=currency_code,
        )

        log_event(
            "DATABASE_WRITE_COMPLETE",
            handler=self.__class__.__name__,
            inserted=total_written,
            skipped=skipped_rows,
            warnings=warnings,
        )

        result.status = "success"
        result.inserted = total_written
        result.finished_at = datetime.utcnow()
        result.summary = (
            f"Inserted {total_written} marketing rows into fact_marketing_daily; skipped {skipped_rows}."
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
        cache_key = (
            campaign_id,
            self._normalized_key(adset_external_id),
            self._normalized_key(adset_name),
        )

        if cache_key[1] == "" and cache_key[2] == "":
            surrogate_name = self._fallback_adset_name(values, row_index)
            if surrogate_name:
                adset_name = surrogate_name
                cache_key = (campaign_id, "", self._normalized_key(adset_name))
                log_event(
                    "ROW_ADSET_SURROGATE_ASSIGNED",
                    handler=self.__class__.__name__,
                    row_index=row_index,
                    surrogate_name=surrogate_name,
                )
            else:
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
        cache_key = (
            adset_id,
            self._normalized_key(ad_external_id),
            self._normalized_key(ad_name),
        )

        if cache_key[1] == "" and cache_key[2] == "":
            surrogate_name = self._fallback_ad_name(values, row_index, ad_name)
            if surrogate_name:
                ad_name = surrogate_name
                cache_key = (adset_id, "", self._normalized_key(ad_name))
                log_event(
                    "ROW_AD_SURROGATE_ASSIGNED",
                    handler=self.__class__.__name__,
                    row_index=row_index,
                    surrogate_name=surrogate_name,
                )
            else:
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
    require_adset_inputs = False
    require_ad_inputs = False
    # Region extracts do not expose ad group or ad level identifiers.  Treat the
    # subregion label as the ad set/ad surrogate so the handler can still create
    # dimension rows (scoped to the campaign) and persist fact records.
    adset_name_fields = ("subregion", "campaign_name")
    ad_name_fields = ("subregion", "campaign_name")
    metric_specs = {
        "spend": MetricSpec("cost", parse_decimal),
        "impressions": MetricSpec("impressions", parse_int),
        "clicks": MetricSpec("clicks_destination", parse_int),
        "conversions": MetricSpec("conversions", parse_int),
        "frequency": MetricSpec("frequency", parse_decimal),
    }

    def _region_surrogate(self, values: dict[str, str], row_index: int) -> str:
        for field in ("subregion", "campaign_name"):
            candidate = (values.get(field, "") or "").strip()
            if candidate:
                return candidate
        return f"region_row_{row_index}"

    def _fallback_adset_name(
        self, values: dict[str, str], row_index: int
    ) -> str | None:
        return self._region_surrogate(values, row_index)

    def _fallback_ad_name(
        self, values: dict[str, str], row_index: int, adset_name: str | None
    ) -> str | None:
        return adset_name or self._region_surrogate(values, row_index)


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
