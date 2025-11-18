"""Repository for Meta DMA files."""
from __future__ import annotations

from app.repositories.files.base import PlatformFileRepository
from app.schemas.ingestion import IngestionPlatform


class MetaDMARepository(PlatformFileRepository):
    def __init__(self) -> None:
        super().__init__(IngestionPlatform.META, "dma_performance_meta.csv")


__all__ = ["MetaDMARepository"]
