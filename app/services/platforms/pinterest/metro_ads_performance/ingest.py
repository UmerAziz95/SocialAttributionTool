"""Ingestion service for Pinterest metro ads files."""
from __future__ import annotations

from app.repositories.files.pinterest.metro_ads_performance import (
    PinterestMetroRepository,
)
from app.services.platforms.base import PlatformFileIngestionService


class PinterestMetroIngestionService(PlatformFileIngestionService):
    def __init__(self) -> None:
        super().__init__(PinterestMetroRepository())


__all__ = ["PinterestMetroIngestionService"]
