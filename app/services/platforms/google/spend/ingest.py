"""Ingestion service for Google spend files."""
from __future__ import annotations

from app.repositories.files.google.spend import GoogleSpendRepository
from app.services.platforms.base import PlatformFileIngestionService


class GoogleSpendIngestionService(PlatformFileIngestionService):
    def __init__(self) -> None:
        super().__init__(GoogleSpendRepository())


__all__ = ["GoogleSpendIngestionService"]
