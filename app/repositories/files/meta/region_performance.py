"""Repository for Meta region files."""
from __future__ import annotations

from app.repositories.files.base import PlatformFileRepository
from app.schemas.ingestion import IngestionPlatform


class MetaRegionRepository(PlatformFileRepository):
    def __init__(self) -> None:
        super().__init__(IngestionPlatform.META, "region_performance_meta.csv")


__all__ = ["MetaRegionRepository"]
