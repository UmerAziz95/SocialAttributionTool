"""Repository for TikTok by DMA extracts."""
from __future__ import annotations

from app.repositories.files.base import PlatformFileRepository
from app.schemas.ingestion import IngestionPlatform


class TikTokByDMARepository(PlatformFileRepository):
    def __init__(self) -> None:
        super().__init__(IngestionPlatform.TIKTOK, "tiktok_by_dma.csv")


__all__ = ["TikTokByDMARepository"]
