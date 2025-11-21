"""Normalization service for Meta region files."""
from __future__ import annotations

from app.repositories.files.meta.region_performance import MetaRegionRepository
from app.services.platforms.base import FileNormalizationService


class MetaRegionNormalizationService(FileNormalizationService):
    def __init__(self) -> None:
        super().__init__(MetaRegionRepository())


__all__ = ["MetaRegionNormalizationService"]
