"""Repository for TikTok by Region extracts."""
from __future__ import annotations

from app.repositories.files.base import PlatformFileRepository
from app.schemas.ingestion import IngestionPlatform


class TikTokByRegionRepository(PlatformFileRepository):
    def __init__(self) -> None:
        super().__init__(IngestionPlatform.TIKTOK, "tiktok_by_region.csv")


__all__ = ["TikTokByRegionRepository"]
