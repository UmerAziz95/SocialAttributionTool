"""Repository for Shopify sales files."""
from __future__ import annotations

from app.repositories.files.base import PlatformFileRepository
from app.schemas.ingestion import IngestionPlatform


class ShopifySalesRepository(PlatformFileRepository):
    def __init__(self) -> None:
        super().__init__(IngestionPlatform.SHOPIFY, "shopify_sales_dimensions.csv")


__all__ = ["ShopifySalesRepository"]
