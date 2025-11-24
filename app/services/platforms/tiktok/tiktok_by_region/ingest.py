"""Ingestion service for TikTok by Region files."""
from __future__ import annotations

from app.repositories.files.tiktok.tiktok_by_region import TikTokByRegionRepository
from app.services.platforms.base import PlatformFileIngestionService


class TikTokByRegionIngestionService(PlatformFileIngestionService):
    def __init__(self) -> None:
        super().__init__(TikTokByRegionRepository())


__all__ = ["TikTokByRegionIngestionService"]
