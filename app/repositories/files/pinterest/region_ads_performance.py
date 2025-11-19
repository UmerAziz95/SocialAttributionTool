"""Repository for Pinterest region performance files."""
from __future__ import annotations

from app.repositories.files.base import PlatformFileRepository
from app.schemas.ingestion import IngestionPlatform


class PinterestRegionRepository(PlatformFileRepository):
    def __init__(self) -> None:
        super().__init__(
            IngestionPlatform.PINTEREST,
            "region+ads_performance_pinterest.csv",
        )


__all__ = ["PinterestRegionRepository"]
