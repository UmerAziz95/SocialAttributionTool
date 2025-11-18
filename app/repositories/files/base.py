"""Repository helpers for locating uploaded and normalized files."""
from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException

from app.schemas.ingestion import IngestionPlatform
from app.services.ingestion.storage import resolve_uploaded_path
from app.services.ingestion.utils import is_normalized_filename


class PlatformFileRepository:
    """Resolves source and normalized files for a specific platform."""

    def __init__(self, platform: IngestionPlatform, default_filename: str) -> None:
        self._platform = platform
        self._default_filename = default_filename

    def _clean_name(self, filename: str | None) -> Path:
        candidate = filename or self._default_filename
        candidate = candidate.strip()
        if not candidate:
            raise HTTPException(
                status_code=400,
                detail="filename must be provided",
            )
        path = Path(candidate)
        if path.is_absolute():
            return path
        return Path(path.name)

    def _normalized_candidate(self, path: Path) -> Path:
        if is_normalized_filename(path):
            return path
        return path.with_name(f"{path.stem}__normalized.csv")

    def _source_candidate(self, path: Path) -> Path:
        if not is_normalized_filename(path):
            return path
        stem = path.stem
        if stem.endswith("__normalized"):
            stem = stem[: -len("__normalized")]
        return path.with_name(f"{stem}{path.suffix}")

    def resolve_source(self, filename: str | None = None) -> Path:
        """Return the path to the uploaded (non-normalized) file."""

        path = self._clean_name(filename)
        if is_normalized_filename(path):
            path = self._source_candidate(path)
        resolved = resolve_uploaded_path(path, self._platform)
        if is_normalized_filename(resolved):
            raise HTTPException(
                status_code=400,
                detail=(
                    f"'{resolved.name}' is already normalized — upload the raw file "
                    "or request normalization instead."
                ),
            )
        return resolved

    def resolve_normalized(self, filename: str | None = None) -> Path:
        """Return the normalized copy for the requested file."""

        path = self._clean_name(filename)
        try:
            resolved = resolve_uploaded_path(path, self._platform)
        except HTTPException:
            normalized_name = self._normalized_candidate(path)
            if normalized_name == path:
                raise
            resolved = resolve_uploaded_path(normalized_name, self._platform)
        if is_normalized_filename(resolved):
            return resolved
        normalized_path = self._normalized_candidate(resolved)
        if normalized_path.exists():
            return normalized_path
        raise HTTPException(
            status_code=404,
            detail=(
                f"Normalized copy for '{resolved.name}' does not exist. Run the "
                "normalization endpoint first."
            ),
        )


__all__ = ["PlatformFileRepository"]
