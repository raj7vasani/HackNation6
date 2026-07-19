"""Multi-file ingestion: detect the shared key and left-join (IMPLEMENTATION_NOTES §7)."""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from .readers import IngestedFile

# Common NHANES subject key; used as a preferred default.
DEFAULT_KEYS = ("SEQN", "subject_id", "id", "ID")


@dataclass
class JoinResult:
    df: pd.DataFrame
    key: str | None
    files: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)  # columns supplied by >1 file
    column_source: dict[str, str] = field(default_factory=dict)  # column → source file


def detect_join_key(files: list[IngestedFile]) -> str | None:
    """Prefer a well-known key present in all files; else any common column."""
    if not files:
        return None
    common = set(files[0].df.columns)
    for f in files[1:]:
        common &= set(f.df.columns)
    for key in DEFAULT_KEYS:
        if key in common:
            return key
    return next(iter(common)) if common else None


def join_files(files: list[IngestedFile], key: str | None = None) -> JoinResult:
    """Left-join all files onto an anchor. Surface overlapping non-key columns."""
    if not files:
        raise ValueError("No files to join.")

    if len(files) == 1:
        f = files[0]
        return JoinResult(
            df=f.df.copy(),
            key=key or detect_join_key(files),
            files=[f.name],
            column_source={c: f.name for c in f.df.columns},
        )

    key = key or detect_join_key(files)
    if key is None:
        raise ValueError("Could not detect a shared join key across files.")

    # Anchor = file with the most rows (usually demographics).
    anchor = max(files, key=lambda f: len(f.df))
    others = [f for f in files if f is not anchor]

    merged = anchor.df.copy()
    column_source = {c: anchor.name for c in anchor.df.columns}
    conflicts: list[str] = []

    for f in others:
        overlap = (set(f.df.columns) & set(merged.columns)) - {key}
        if overlap:
            conflicts.extend(sorted(overlap))
        # Only bring in the key + columns not already present, to avoid silently
        # picking one source for a conflicting column.
        new_cols = [c for c in f.df.columns if c == key or c not in merged.columns]
        merged = merged.merge(f.df[new_cols], on=key, how="left")
        for c in new_cols:
            if c != key:
                column_source[c] = f.name

    return JoinResult(
        df=merged,
        key=key,
        files=[f.name for f in files],
        conflicts=sorted(set(conflicts)),
        column_source=column_source,
    )
