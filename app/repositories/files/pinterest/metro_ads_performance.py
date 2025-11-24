"""Repository for Pinterest metro performance files."""
from __future__ import annotations

from app.repositories.files.base import PlatformFileRepository
from app.schemas.ingestion import IngestionPlatform


class PinterestMetroRepository(PlatformFileRepository):
    def __init__(self) -> None:
        super().__init__(IngestionPlatform.PINTEREST, "metro+ads_performance_pinterest.csv")


__all__ = ["PinterestMetroRepository"]
