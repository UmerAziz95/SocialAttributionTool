"""Registry for platform/file-specific services."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from app.schemas.ingestion import IngestionPlatform
from app.services.platforms.base import (
    FileNormalizationService,
    PlatformFileIngestionService,
)
from app.services.platforms.google import (
    GoogleSpendIngestionService,
    GoogleSpendNormalizationService,
)
from app.services.platforms.meta import (
    MetaDMAIngestionService,
    MetaDMANormalizationService,
    MetaRegionIngestionService,
    MetaRegionNormalizationService,
)
from app.services.platforms.pinterest import (
    PinterestMetroIngestionService,
    PinterestMetroNormalizationService,
    PinterestRegionIngestionService,
    PinterestRegionNormalizationService,
)
from app.services.platforms.shopify import (
    ShopifySalesIngestionService,
    ShopifySalesNormalizationService,
    ShopifySessionsIngestionService,
    ShopifySessionsNormalizationService,
)
from app.services.platforms.tiktok import (
    TikTokByAdsFreqIngestionService,
    TikTokByAdsFreqNormalizationService,
    TikTokByDMAIngestionService,
    TikTokByDMANormalizationService,
    TikTokByRegionIngestionService,
    TikTokByRegionNormalizationService,
)


def _normalize_key(filename: str) -> str:
    cleaned = Path(filename).name.lower()
    if cleaned.endswith("__normalized.csv"):
        cleaned = cleaned[: -len("__normalized.csv")] + ".csv"
    if cleaned.endswith(".csv"):
        cleaned = cleaned[: -len(".csv")]
    # For Google files, match any filename containing "google"
    if "google" in cleaned:
        return "google"
    return cleaned


INGESTION_REGISTRY: dict[
    IngestionPlatform, dict[str, PlatformFileIngestionService]
] = {
    IngestionPlatform.TIKTOK: {
        "tiktok_by_dma": TikTokByDMAIngestionService(),
        "tiktok_by_region": TikTokByRegionIngestionService(),
        "tiktok_by_ads_freq_addtocart": TikTokByAdsFreqIngestionService(),
    },
    IngestionPlatform.META: {
        "dma_performance_meta": MetaDMAIngestionService(),
        "region_performance_meta": MetaRegionIngestionService(),
    },
    IngestionPlatform.PINTEREST: {
        "metro+ads_performance_pinterest": PinterestMetroIngestionService(),
        "region+ads_performance_pinterest": PinterestRegionIngestionService(),
    },
    IngestionPlatform.GOOGLE: {
        "google_spend": GoogleSpendIngestionService(),
        "google": GoogleSpendIngestionService(),
    },
    IngestionPlatform.SHOPIFY: {
        "shopify_sales_dimensions": ShopifySalesIngestionService(),
        "shopify_session_dimensions": ShopifySessionsIngestionService(),
    },
}

NORMALIZATION_REGISTRY: dict[
    IngestionPlatform, dict[str, FileNormalizationService]
] = {
    IngestionPlatform.TIKTOK: {
        "tiktok_by_dma": TikTokByDMANormalizationService(),
        "tiktok_by_region": TikTokByRegionNormalizationService(),
        "tiktok_by_ads_freq_addtocart": TikTokByAdsFreqNormalizationService(),
    },
    IngestionPlatform.META: {
        "dma_performance_meta": MetaDMANormalizationService(),
        "region_performance_meta": MetaRegionNormalizationService(),
    },
    IngestionPlatform.PINTEREST: {
        "metro+ads_performance_pinterest": PinterestMetroNormalizationService(),
        "region+ads_performance_pinterest": PinterestRegionNormalizationService(),
    },
    IngestionPlatform.GOOGLE: {
        "google_spend": GoogleSpendNormalizationService(),
        "google": GoogleSpendNormalizationService(),
    },
    IngestionPlatform.SHOPIFY: {
        "shopify_sales_dimensions": ShopifySalesNormalizationService(),
        "shopify_session_dimensions": ShopifySessionsNormalizationService(),
    },
}


def get_ingestion_service_for_file(
    platform: IngestionPlatform, filename: str
) -> Optional[PlatformFileIngestionService]:
    registry = INGESTION_REGISTRY.get(platform)
    if not registry:
        return None
    return registry.get(_normalize_key(filename))


def get_normalization_service_for_file(
    platform: IngestionPlatform, filename: str
) -> Optional[FileNormalizationService]:
    registry = NORMALIZATION_REGISTRY.get(platform)
    if not registry:
        return None
    return registry.get(_normalize_key(filename))


__all__ = [
    "get_ingestion_service_for_file",
    "get_normalization_service_for_file",
]
