"""Normalization service for Meta DMA files."""
from __future__ import annotations

from app.repositories.files.meta.dma_performance import MetaDMARepository
from app.services.platforms.base import FileNormalizationService


class MetaDMANormalizationService(FileNormalizationService):
    def __init__(self) -> None:
        super().__init__(MetaDMARepository())


__all__ = ["MetaDMANormalizationService"]
