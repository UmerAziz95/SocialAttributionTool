"""Handler for Google spend extracts."""
from __future__ import annotations

from typing import Iterable

from sqlalchemy import delete, insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.marketing import FactMarketingDaily
from app.services.ingestion.base import IngestionHandler
from app.services.ingestion.dimensions import DimensionResolver, ensure_date_id
from app.services.ingestion.logging import log_event
from app.services.ingestion.parsers import parse_date, parse_decimal
from app.services.ingestion.types import IngestionContext, IngestionResult
from app.services.ingestion.utils import NormalizationResult


class GoogleSpendHandler(IngestionHandler):
    file_patterns = ("google",)
    required_columns: Iterable[str] = ("spend_by_country_row_only",)

    def matches(self, file_path: str) -> bool:  # type: ignore[override]
        return any(pattern in file_path.lower() for pattern in self.file_patterns)

    async def validate(
        self, normalized: NormalizationResult, context: IngestionContext
    ) -> None:  # type: ignore[override]
        self._ensure_required_columns(normalized, self.required_columns)
        for key in ("platform_id", "account_id", "campaign_id", "adset_id", "ad_id"):
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
        current_date_id: int | None = None

        for index, row in enumerate(normalized.rows, start=1):
            values = row.values
            label = values.get("spend_by_country_row_only", "")
            maybe_date = parse_date(label)
            if maybe_date:
                current_date_id = await ensure_date_id(session, maybe_date)
                log_event(
                    "GOOGLE_SECTION_DATE",
                    handler=self.__class__.__name__,
                    row_index=index,
                    label=label,
                    date=str(maybe_date),
                    date_id=current_date_id,
                )
                continue

            spend = parse_decimal(values.get("unnamed_1", ""))
            if spend is None:
                log_event(
                    "GOOGLE_ROW_SKIPPED_NO_SPEND",
                    handler=self.__class__.__name__,
                    row_index=index,
                    label=label,
                )
                continue
            if current_date_id is None:
                result.warnings.append("Skipping Google row without resolved date")
                result.skipped += 1
                log_event(
                    "GOOGLE_ROW_SKIPPED_NO_DATE",
                    handler=self.__class__.__name__,
                    row_index=index,
                    label=label,
                )
                continue

            region_id = resolver.resolve_mapping("region_map", label)
            dma_id = resolver.resolve_mapping("dma_map", label)
            payload.append(
                {
                    "platform_id": platform_id,
                    "account_id": account_id,
                    "campaign_id": campaign_id,
                    "adset_id": adset_id,
                    "ad_id": ad_id,
                    "date_id": current_date_id,
                    "region_id": region_id,
                    "dma_id": dma_id,
                    "attribution_id": attribution_id,
                    "currency_code": currency_code,
                    "spend": spend,
                }
            )
            log_event(
                "GOOGLE_ROW_READY",
                handler=self.__class__.__name__,
                row_index=index,
                label=label,
                date_id=current_date_id,
                region_id=region_id,
                dma_id=dma_id,
                spend=spend,
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
            return result

        date_ids = {item["date_id"] for item in payload}
        log_event(
            "DATABASE_WRITE_BEGIN",
            handler=self.__class__.__name__,
            payload_rows=len(payload),
            unique_dates=len(date_ids),
        )
        delete_stmt = delete(FactMarketingDaily).where(
            FactMarketingDaily.platform_id == platform_id,
            FactMarketingDaily.account_id == account_id,
            FactMarketingDaily.campaign_id == campaign_id,
            FactMarketingDaily.adset_id == adset_id,
            FactMarketingDaily.ad_id == ad_id,
            FactMarketingDaily.date_id.in_(date_ids),
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
        return result
