"""Ingestion service for TikTok by DMA files."""
from __future__ import annotations

from app.repositories.files.tiktok.tiktok_by_dma import TikTokByDMARepository
from app.services.platforms.base import PlatformFileIngestionService


class TikTokByDMAIngestionService(PlatformFileIngestionService):
    def __init__(self) -> None:
        super().__init__(TikTokByDMARepository())


__all__ = ["TikTokByDMAIngestionService"]
