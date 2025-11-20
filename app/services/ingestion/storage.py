"""Helpers for locating uploaded and normalized files on disk."""
from __future__ import annotations

from pathlib import Path, PureWindowsPath

from fastapi import HTTPException

from app.schemas.ingestion import IngestionPlatform
from app.services.ingestion.logging import log_event


UPLOAD_ROOT = Path("data/uploads").resolve()


def resolve_uploaded_path(
    provided: str | Path, platform: IngestionPlatform | None = None
) -> Path:
    """Locate an uploaded file based on the provided path or filename.

    The upload endpoint returns an absolute path, but users may also supply just the
    filename or a path that differs from the server's runtime root (for example when
    following documentation examples). This helper searches a few sensible locations
    so ingestion succeeds as long as the file exists within the uploads directory.
    """

    raw_value = str(provided).strip()
    if not raw_value:
        raise HTTPException(status_code=400, detail="file_path must be provided")

    platform_dir = UPLOAD_ROOT / platform.value if platform else None
    normalized = raw_value.replace("\\", "/")

    candidates: list[Path] = []
    seen: set[str] = set()

    def add_candidate(path: Path) -> None:
        candidate_str = str(path)
        if not candidate_str or candidate_str in seen:
            return
        candidates.append(path)
        seen.add(candidate_str)

    add_candidate(Path(raw_value))

    if "\\" in raw_value or ":" in raw_value:
        add_candidate(Path(PureWindowsPath(raw_value)))

    marker = "/data/uploads/"
    if marker in normalized:
        suffix = normalized.split(marker, 1)[1]
        add_candidate(UPLOAD_ROOT / suffix)

    if platform_dir and not Path(raw_value).is_absolute():
        add_candidate(platform_dir / raw_value)

    filename = Path(normalized).name
    if filename:
        if platform_dir:
            add_candidate(platform_dir / filename)
        else:
            add_candidate(UPLOAD_ROOT / filename)
        try:
            for subdir in UPLOAD_ROOT.iterdir():
                if not subdir.is_dir():
                    continue
                add_candidate(subdir / filename)
        except FileNotFoundError:
            pass

    for candidate in candidates:
        try:
            candidate_path = (
                candidate if candidate.is_absolute() else candidate.resolve()
            )
        except OSError:
            continue

        if candidate_path.exists():
            log_event(
                "RESOLVE_PATH_SUCCESS",
                provided=raw_value,
                resolved=candidate_path,
            )
            return candidate_path

    # Fall back to case-insensitive matching within the platform directory when the
    # caller supplied a filename whose casing differs from what was uploaded (for
    # example "tiktok_by_ads_freq_AddToCart.csv"). This keeps ingestion resilient
    # to Windows/OSX uploads while still respecting the per-platform folder.
    filename_lower = Path(normalized).name.lower()
    if filename_lower and platform_dir and platform_dir.exists():
        for entry in platform_dir.iterdir():
            if entry.is_file() and entry.name.lower() == filename_lower:
                log_event(
                    "RESOLVE_PATH_SUCCESS",
                    provided=raw_value,
                    resolved=entry,
                    matched_case_insensitive=True,
                )
                return entry

    raise HTTPException(
        status_code=404,
        detail=(
            f"file_path '{raw_value}' does not exist in expected upload directories"
        ),
    )


__all__ = ["resolve_uploaded_path", "UPLOAD_ROOT"]
