"""Handlers for Shopify sales and session files."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.marketing import FactShopifyDaily, StgShopifyDailyCity
from app.services.ingestion.base import IngestionHandler
from app.services.ingestion.dimensions import DimensionResolver, ensure_date_id
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


class ShopifySalesHandler(ShopifyBaseHandler):
    file_patterns = ("shopify_sales_dimensions",)
    required_columns = ("day", "shipping_country", "shipping_city", "shipping_region")
    metric_specs = {
        "orders": ShopifyMetricSpec("orders", parse_decimal),
        "gross_sales": ShopifyMetricSpec("gross_sales", parse_decimal),
        "shipping": ShopifyMetricSpec("shipping", parse_decimal),
        "refunds": ShopifyMetricSpec("refunds", parse_decimal),
        "total_sales": ShopifyMetricSpec("total_sales", parse_decimal),
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
        attribution_id = resolver.optional("attribution_id")

        payload: list[dict] = []
        for row in normalized.rows:
            values = row.values
            parsed_date = parse_date(values.get(self.date_column, ""))
            if not parsed_date:
                result.skipped += 1
                result.warnings.append("Skipping row without valid date")
                continue
            date_id = await ensure_date_id(session, parsed_date)

            country_iso = resolver.resolve_mapping("country_iso_map", values.get(self.country_column, ""))
            region_code = resolver.resolve_mapping("region_code_map", values.get(self.region_column, ""))
            city_name = (values.get(self.city_column, "") or "").strip()
            if not country_iso or not region_code or not city_name:
                result.skipped += 1
                result.warnings.append("Missing location mapping for Shopify sales row")
                continue

            record = {
                "date_id": date_id,
                "platform_id": platform_id,
                "account_id": account_id,
                "country_iso2": country_iso,
                "region_code": region_code,
                "city_name_norm": city_name.lower(),
                "country_id": resolver.resolve_mapping("country_map", values.get(self.country_column, "")),
                "region_id": resolver.resolve_mapping("region_map", values.get(self.region_column, "")),
                "city_id": resolver.resolve_mapping("city_map", values.get(self.city_column, "")),
                "attribution_id": attribution_id,
                "_source_file": context.file_path.name,
            }
            for target_column, spec in self.metric_specs.items():
                record[target_column] = spec.parser(values.get(spec.column, ""))
            payload.append(record)

        if context.dry_run or not payload:
            result.inserted = len(payload)
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
        await session.execute(stmt)
        await session.commit()

        result.inserted = len(payload)
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
        "orders": ShopifyMetricSpec("sessions_that_completed_checkout", parse_decimal),
        "revenue": ShopifyMetricSpec("online_store_visitors", parse_decimal),
    }

    async def ingest(
        self,
        session: AsyncSession,
        normalized: NormalizationResult,
        context: IngestionContext,
    ) -> IngestionResult:  # type: ignore[override]
        resolver = DimensionResolver(context.column_map)
        result = IngestionResult()

        payload: list[dict] = []
        for row in normalized.rows:
            values = row.values
            parsed_date = parse_date(values.get(self.date_column, ""))
            if not parsed_date:
                result.skipped += 1
                result.warnings.append("Skipping Shopify session row without date")
                continue
            date_id = await ensure_date_id(session, parsed_date)

            country_id = resolver.resolve_mapping("country_map", values.get(self.country_column, ""))
            region_id = resolver.resolve_mapping("region_map", values.get(self.region_column, ""))
            city_id = resolver.resolve_mapping("city_map", values.get(self.city_column, ""))
            postal_id = resolver.resolve_mapping("postal_map", values.get("session_postal_code", ""))

            if None in (country_id, region_id, city_id, postal_id):
                result.skipped += 1
                result.warnings.append("Missing dimension mapping for Shopify session row")
                continue

            record = {
                "date_id": date_id,
                "country_id": country_id,
                "region_id": region_id,
                "city_id": city_id,
                "postal_id": postal_id,
                "currency_code": context.currency_code,
                "add_to_cart": None,
            }
            for target_column, spec in self.metric_specs.items():
                record[target_column] = spec.parser(values.get(spec.column, ""))
            payload.append(record)

        if context.dry_run or not payload:
            result.inserted = len(payload)
            return result

        stmt = insert(FactShopifyDaily).values(payload)
        update_columns = {col: stmt.excluded[col] for col in self.metric_specs.keys()}
        stmt = stmt.on_conflict_do_update(
            index_elements=[
                FactShopifyDaily.date_id,
                FactShopifyDaily.country_id,
                FactShopifyDaily.region_id,
                FactShopifyDaily.city_id,
                FactShopifyDaily.postal_id,
            ],
            set_=update_columns,
        )
        await session.execute(stmt)
        await session.commit()

        result.inserted = len(payload)
        return result
