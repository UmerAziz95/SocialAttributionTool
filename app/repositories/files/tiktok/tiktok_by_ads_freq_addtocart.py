"""Repository for TikTok ads frequency + add-to-cart extracts."""
from __future__ import annotations

from app.repositories.files.base import PlatformFileRepository
from app.schemas.ingestion import IngestionPlatform


class TikTokByAdsFreqRepository(PlatformFileRepository):
    def __init__(self) -> None:
        super().__init__(
            IngestionPlatform.TIKTOK,
            "tiktok_by_ads_freq_addtocart.csv",
        )


__all__ = ["TikTokByAdsFreqRepository"]
