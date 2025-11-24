"""Normalization service for TikTok ads frequency files."""
from __future__ import annotations

from app.repositories.files.tiktok.tiktok_by_ads_freq_addtocart import (
    TikTokByAdsFreqRepository,
)
from app.services.platforms.base import FileNormalizationService


class TikTokByAdsFreqNormalizationService(FileNormalizationService):
    def __init__(self) -> None:
        super().__init__(TikTokByAdsFreqRepository())


__all__ = ["TikTokByAdsFreqNormalizationService"]
