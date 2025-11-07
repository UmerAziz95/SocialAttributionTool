"""Collection of ingestion handlers."""
from __future__ import annotations

from typing import Sequence

from app.services.ingestion.base import IngestionHandler

from .google import GoogleSpendHandler
from .marketing import (
    MetaDMAHandler,
    MetaRegionHandler,
    PinterestDMAHandler,
    PinterestRegionHandler,
    TikTokAdsHandler,
    TikTokDMAHandler,
    TikTokRegionHandler,
)
from .shopify import ShopifySalesHandler, ShopifySessionsHandler

HANDLERS: Sequence[IngestionHandler] = (
    MetaDMAHandler(),
    MetaRegionHandler(),
    PinterestDMAHandler(),
    PinterestRegionHandler(),
    TikTokDMAHandler(),
    TikTokRegionHandler(),
    TikTokAdsHandler(),
    GoogleSpendHandler(),
    ShopifySalesHandler(),
    ShopifySessionsHandler(),
)

__all__ = ["HANDLERS"]
