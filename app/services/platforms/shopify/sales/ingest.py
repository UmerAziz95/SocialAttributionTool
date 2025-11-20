"""Ingestion service for Shopify sales files."""
from __future__ import annotations

from app.repositories.files.shopify.sales import ShopifySalesRepository
from app.services.platforms.base import PlatformFileIngestionService


class ShopifySalesIngestionService(PlatformFileIngestionService):
    def __init__(self) -> None:
        super().__init__(ShopifySalesRepository())


__all__ = ["ShopifySalesIngestionService"]
