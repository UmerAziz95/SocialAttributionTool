"""Normalization service for Shopify session files."""
from __future__ import annotations

from app.repositories.files.shopify.sessions import ShopifySessionsRepository
from app.services.platforms.base import FileNormalizationService


class ShopifySessionsNormalizationService(FileNormalizationService):
    def __init__(self) -> None:
        super().__init__(ShopifySessionsRepository())


__all__ = ["ShopifySessionsNormalizationService"]
