"""Repository for Shopify session files."""
from __future__ import annotations

from app.repositories.files.base import PlatformFileRepository
from app.schemas.ingestion import IngestionPlatform


class ShopifySessionsRepository(PlatformFileRepository):
    def __init__(self) -> None:
        super().__init__(IngestionPlatform.SHOPIFY, "shopify_session_dimensions.csv")


__all__ = ["ShopifySessionsRepository"]
