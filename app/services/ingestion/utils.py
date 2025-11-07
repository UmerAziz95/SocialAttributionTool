"""Utility helpers used by the ingestion pipeline."""
from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

from fastapi import HTTPException


CANDIDATE_ENCODINGS: Sequence[str] = ("utf-8", "utf-8-sig", "latin-1")
CANDIDATE_DELIMITERS: Sequence[str] = (",", "\t", ";")


@dataclass(slots=True)
class NormalizedRow:
    """A normalized row from an input file."""

    values: dict[str, str]


@dataclass(slots=True)
class NormalizationResult:
    """Details about a normalized file."""

    path: Path
    headers: list[str]
    rows: list[NormalizedRow]
    encoding: str
    delimiter: str


def _normalize_header(header: str) -> str:
    header = header.strip().lower()
    header = re.sub(r"[\s\-/]+", "_", header)
    header = re.sub(r"[^0-9a-zA-Z_]+", "", header)
    return header.strip("_")


def _drop_blank_rows(rows: Iterable[list[str]]) -> list[list[str]]:
    cleaned: list[list[str]] = []
    for row in rows:
        if all((cell or "").strip() == "" for cell in row):
            continue
        cleaned.append([cell.strip() for cell in row])
    return cleaned


def detect_encoding(path: Path) -> str:
    for encoding in CANDIDATE_ENCODINGS:
        try:
            path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
        else:
            return encoding
    raise HTTPException(status_code=400, detail=f"Unable to detect encoding for {path.name}")


def detect_delimiter(sample: str) -> str:
    max_hits = -1
    selected = ","
    for delimiter in CANDIDATE_DELIMITERS:
        hits = sample.count(delimiter)
        if hits > max_hits:
            max_hits = hits
            selected = delimiter
    return selected


def normalize_file(path: Path) -> NormalizationResult:
    encoding = detect_encoding(path)
    raw_text = path.read_text(encoding=encoding)

    first_chunk = raw_text.splitlines()[:5]
    sample = "\n".join(first_chunk)
    delimiter = detect_delimiter(sample)

    reader = csv.reader(io.StringIO(raw_text), delimiter=delimiter)

    headers: list[str] | None = None
    data_rows: list[list[str]] = []
    for row in reader:
        if not any((cell or "").strip() for cell in row):
            continue
        if headers is None:
            headers = [_normalize_header(cell) for cell in row]
            continue
        data_rows.append(row)

    if headers is None:
        raise HTTPException(status_code=400, detail=f"{path.name} does not contain a header row")

    data_rows = _drop_blank_rows(data_rows)

    # Ensure consistent row length.
    normalized_rows: list[NormalizedRow] = []
    for row in data_rows:
        values = {}
        for index, header in enumerate(headers):
            values[header] = row[index].strip() if index < len(row) else ""
        normalized_rows.append(NormalizedRow(values))

    normalized_path = path.with_name(f"{path.stem}__normalized.csv")
    with normalized_path.open("w", encoding="utf-8", newline="") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=headers)
        writer.writeheader()
        for row in normalized_rows:
            writer.writerow(row.values)

    return NormalizationResult(
        path=normalized_path,
        headers=headers,
        rows=normalized_rows,
        encoding=encoding,
        delimiter=delimiter,
    )
