"""Normalization service for Pinterest region ads files."""
from __future__ import annotations

from app.repositories.files.pinterest.region_ads_performance import (
    PinterestRegionRepository,
)
from app.services.platforms.base import FileNormalizationService


class PinterestRegionNormalizationService(FileNormalizationService):
    def __init__(self) -> None:
        super().__init__(PinterestRegionRepository())


__all__ = ["PinterestRegionNormalizationService"]
