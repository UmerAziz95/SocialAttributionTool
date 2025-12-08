"""Handlers for Shopify sales and session files."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.marketing import StgShopifyDailyCity
from app.services.ingestion.base import IngestionHandler
from app.services.ingestion.dimensions import (
    DimensionResolver,
    ensure_account_id,
    ensure_date_id,
    ensure_platform_id,
)
from app.services.ingestion.logging import log_event
from app.services.ingestion.parsers import parse_date, parse_decimal
from app.services.ingestion.types import IngestionContext, IngestionResult
from app.services.ingestion.utils import NormalizationResult


@dataclass(slots=True)
class ShopifyMetricSpec:
    column: str
    parser: Callable[[str], object]


class ShopifyBaseHandler(IngestionHandler):
    file_patterns: tuple[str, ...] = ()
    required_columns: Iterable[str] = ()
    date_column: str = "day"
    country_column: str = "shipping_country"
    region_column: str = "shipping_region"
    city_column: str = "shipping_city"
    metric_specs: dict[str, ShopifyMetricSpec] = {}

    def matches(self, file_path: str) -> bool:  # type: ignore[override]
        return any(pattern in file_path.lower() for pattern in self.file_patterns)

    async def validate(
        self, normalized: NormalizationResult, context: IngestionContext
    ) -> None:  # type: ignore[override]
        self._ensure_required_columns(normalized, self.required_columns)
        for key in ("platform_id", "account_id"):
            if key not in context.column_map:
                raise ValueError(f"column_map must include '{key}' for Shopify ingestions")

    async def _ensure_dimensions(
        self,
        session: AsyncSession,
        *,
        platform_id: int,
        account_id: int,
    ) -> tuple[int, int]:
        """Ensure platform and account dimensions exist before ingestion."""

        ensured_platform_id = await ensure_platform_id(session, platform_id)
        log_event(
            "PLATFORM_DIMENSION_ENSURED",
            handler=self.__class__.__name__,
            supplied_platform_id=platform_id,
            ensured_platform_id=ensured_platform_id,
        )

        ensured_account_id = await ensure_account_id(
            session,
            account_id,
            ensured_platform_id,
        )
        log_event(
            "ACCOUNT_DIMENSION_ENSURED",
            handler=self.__class__.__name__,
            supplied_account_id=account_id,
            ensured_account_id=ensured_account_id,
            platform_id=ensured_platform_id,
        )

        return ensured_platform_id, ensured_account_id


class ShopifySalesHandler(ShopifyBaseHandler):
    file_patterns = ("shopify_sales_dimensions",)
    required_columns = ("day", "shipping_country", "shipping_city", "shipping_region")
    metric_specs = {
        "orders": ShopifyMetricSpec("orders", parse_decimal),
        "gross_sales": ShopifyMetricSpec("gross_sales", parse_decimal),
        "total_sales": ShopifyMetricSpec("total_sales", parse_decimal),
        "net_sales": ShopifyMetricSpec("net_sales", parse_decimal),
        "duties": ShopifyMetricSpec("duties", parse_decimal),
        "taxes": ShopifyMetricSpec("taxes", parse_decimal),
        "returning_customers": ShopifyMetricSpec("returning_customers", parse_decimal),
        "new_customers": ShopifyMetricSpec("new_customers", parse_decimal),
    }

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
        platform_id, account_id = await self._ensure_dimensions(
            session, platform_id=platform_id, account_id=account_id
        )
        attribution_id = resolver.optional("attribution_id")

        log_event(
            "HANDLER_CONTEXT_RESOLVED",
            handler=self.__class__.__name__,
            platform_id=platform_id,
            account_id=account_id,
            attribution_id=attribution_id,
        )

        payload: list[dict] = []
        for index, row in enumerate(normalized.rows, start=1):
            values = row.values
            raw_date = values.get(self.date_column, "") or ""
            parsed_date = parse_date(raw_date)
            if not parsed_date:
                result.skipped += 1
                result.warnings.append(
                    f"Row {index}: invalid date value '{raw_date}' — provide a parsable date"
                )
                log_event(
                    "SHOPIFY_ROW_SKIPPED_NO_DATE",
                    handler=self.__class__.__name__,
                    row_index=index,
                    raw=values,
                )
                continue
            # Populate the date dimension but store the raw date value in staging
            date_id = await ensure_date_id(session, parsed_date)
            log_event(
                "ROW_DATE_RESOLVED",
                handler=self.__class__.__name__,
                row_index=index,
                date=str(parsed_date),
                date_id=date_id,
            )

            country_raw = (values.get(self.country_column, "") or "").strip()
            region_raw = (values.get(self.region_column, "") or "").strip()
            city_name = (values.get(self.city_column, "") or "").strip()
            country_iso = resolver.resolve_mapping("country_iso_map", country_raw) or country_raw
            region_code = resolver.resolve_mapping("region_code_map", region_raw) or region_raw
            if not country_iso or not region_code or not city_name:
                result.skipped += 1
                result.warnings.append(
                    f"Row {index}: missing location data — provide country/region/city values"
                )
                log_event(
                    "SHOPIFY_ROW_SKIPPED_LOCATION",
                    handler=self.__class__.__name__,
                    row_index=index,
                    raw=values,
                )
                continue

            record = {
                "date_id": parsed_date,
                "platform_id": platform_id,
                "account_id": account_id,
                "country_iso2": country_iso,
                "region_code": region_code,
                "city_name_norm": city_name.lower(),
                "country_id": resolver.resolve_mapping("country_map", country_raw),
                "region_id": resolver.resolve_mapping("region_map", region_raw),
                "city_id": resolver.resolve_mapping("city_map", city_name),
                "attribution_id": attribution_id,
                "_source_file": context.file_path.name,
            }
            for target_column, spec in self.metric_specs.items():
                record[target_column] = spec.parser(values.get(spec.column, ""))
            payload.append(record)
            log_event(
                "ROW_READY",
                handler=self.__class__.__name__,
                row_index=index,
                date_id=date_id,
                country_iso=country_iso,
                region_code=region_code,
                city_name=city_name.lower(),
                metrics={key: record[key] for key in self.metric_specs.keys()},
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
                    f"Dry run prepared {len(payload)} Shopify sales rows for stg_shopify_daily_city; "
                    f"skipped {result.skipped}."
                )
            else:
                result.summary = (
                    "No Shopify sales rows were written; add location mappings or fix data and retry."
                )
            return result

        stmt = insert(StgShopifyDailyCity).values(payload)
        update_columns = {col: stmt.excluded[col] for col in self.metric_specs.keys()}
        update_columns.update({"_source_file": stmt.excluded._source_file})
        stmt = stmt.on_conflict_do_update(
            index_elements=[
                StgShopifyDailyCity.date_id,
                StgShopifyDailyCity.account_id,
                StgShopifyDailyCity.country_iso2,
                StgShopifyDailyCity.region_code,
                StgShopifyDailyCity.city_name_norm,
            ],
            set_=update_columns,
        )
        log_event(
            "DATABASE_WRITE_BEGIN",
            handler=self.__class__.__name__,
            payload_rows=len(payload),
            unique_dates=len({item["date_id"] for item in payload}),
        )
        log_event(
            "UPSERT_DETAILS",
            handler=self.__class__.__name__,
            conflict_keys=[
                "date_id",
                "account_id",
                "country_iso2",
                "region_code",
                "city_name_norm",
            ],
            updated_columns=list(update_columns.keys()),
        )
        await session.execute(stmt)
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
            f"Upserted {len(payload)} Shopify sales rows into stg_shopify_daily_city; skipped {result.skipped}."
        )
        return result


class ShopifySessionsHandler(ShopifyBaseHandler):
    file_patterns = ("shopify_session_dimensions",)
    required_columns = ("day", "session_country", "session_region", "session_city")
    date_column = "day"
    country_column = "session_country"
    region_column = "session_region"
    city_column = "session_city"
    metric_specs = {
        "sessions": ShopifyMetricSpec("sessions", parse_decimal),
        "checkout_sessions": ShopifyMetricSpec("sessions_that_completed_checkout", parse_decimal),
        "online_store_visitors": ShopifyMetricSpec("online_store_visitors", parse_decimal),
    }

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
        platform_id, account_id = await self._ensure_dimensions(
            session, platform_id=platform_id, account_id=account_id
        )
        attribution_id = resolver.optional("attribution_id")

        log_event(
            "HANDLER_CONTEXT_RESOLVED",
            handler=self.__class__.__name__,
            platform_id=platform_id,
            account_id=account_id,
            attribution_id=attribution_id,
        )

        payload: list[dict] = []
        for index, row in enumerate(normalized.rows, start=1):
            values = row.values
            raw_date = values.get(self.date_column, "") or ""
            parsed_date = parse_date(raw_date)
            if not parsed_date:
                result.skipped += 1
                result.warnings.append(
                    f"Row {index}: invalid date value '{raw_date}' — provide a parsable date"
                )
                log_event(
                    "SHOPIFY_ROW_SKIPPED_NO_DATE",
                    handler=self.__class__.__name__,
                    row_index=index,
                    raw=values,
                )
                continue
            date_id = await ensure_date_id(session, parsed_date)
            log_event(
                "ROW_DATE_RESOLVED",
                handler=self.__class__.__name__,
                row_index=index,
                date=str(parsed_date),
                date_id=date_id,
            )

            country_raw = (values.get(self.country_column, "") or "").strip()
            region_raw = (values.get(self.region_column, "") or "").strip()
            city_name = (values.get(self.city_column, "") or "").strip()
            country_iso = resolver.resolve_mapping("country_iso_map", country_raw) or country_raw
            region_code = resolver.resolve_mapping("region_code_map", region_raw) or region_raw
            if not country_iso or not region_code or not city_name:
                result.skipped += 1
                result.warnings.append(
                    f"Row {index}: missing location data — provide country/region/city values"
                )
                log_event(
                    "SHOPIFY_ROW_SKIPPED_LOCATION",
                    handler=self.__class__.__name__,
                    row_index=index,
                    raw=values,
                )
                continue

            record = {
                "date_id": parsed_date,
                "platform_id": platform_id,
                "account_id": account_id,
                "country_iso2": country_iso,
                "region_code": region_code,
                "city_name_norm": city_name.lower(),
                "country_id": resolver.resolve_mapping("country_map", country_raw),
                "region_id": resolver.resolve_mapping("region_map", region_raw),
                "city_id": resolver.resolve_mapping("city_map", city_name),
                "attribution_id": attribution_id,
                "_source_file": normalized.path.name,
            }
            for target_column, spec in self.metric_specs.items():
                record[target_column] = spec.parser(values.get(spec.column, ""))
            payload.append(record)
            log_event(
                "ROW_READY",
                handler=self.__class__.__name__,
                row_index=index,
                date_id=date_id,
                country_iso=country_iso,
                region_code=region_code,
                city_name=city_name.lower(),
                metrics={key: record[key] for key in self.metric_specs.keys()},
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
                    f"Dry run prepared {len(payload)} Shopify session rows for stg_shopify_daily_city; "
                    f"skipped {result.skipped}."
                )
            else:
                result.summary = (
                    "No Shopify session rows were written; add location mappings or fix data and retry."
                )
            return result

        stmt = insert(StgShopifyDailyCity).values(payload)
        update_columns = {col: stmt.excluded[col] for col in self.metric_specs.keys()}
        update_columns.update({"_source_file": stmt.excluded._source_file})
        stmt = stmt.on_conflict_do_update(
            index_elements=[
                StgShopifyDailyCity.date_id,
                StgShopifyDailyCity.account_id,
                StgShopifyDailyCity.country_iso2,
                StgShopifyDailyCity.region_code,
                StgShopifyDailyCity.city_name_norm,
            ],
            set_=update_columns,
        )
        log_event(
            "DATABASE_WRITE_BEGIN",
            handler=self.__class__.__name__,
            payload_rows=len(payload),
            unique_dates=len({item["date_id"] for item in payload}),
        )
        log_event(
            "UPSERT_DETAILS",
            handler=self.__class__.__name__,
            conflict_keys=[
                "date_id",
                "account_id",
                "country_iso2",
                "region_code",
                "city_name_norm",
            ],
            updated_columns=list(update_columns.keys()),
        )
        await session.execute(stmt)
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
            f"Upserted {len(payload)} Shopify session rows into stg_shopify_daily_city; skipped {result.skipped}."
        )
        return result
