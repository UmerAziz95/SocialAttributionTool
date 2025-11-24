"""Repository for Google spend files."""
from __future__ import annotations

from app.repositories.files.base import PlatformFileRepository
from app.schemas.ingestion import IngestionPlatform


class GoogleSpendRepository(PlatformFileRepository):
    def __init__(self) -> None:
        super().__init__(IngestionPlatform.GOOGLE, "google_spend.csv")


__all__ = ["GoogleSpendRepository"]
