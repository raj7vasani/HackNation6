"""Detect and reject longitudinal / time-series inputs (spec §8)."""

from __future__ import annotations

import pandas as pd

_TIME_TOKENS = (
    "date",
    "time",
    "timestamp",
    "visit",
    "day",
    "week",
    "month",
    "cycle_day",
    "datetime",
    "epoch",
)


class LongitudinalInputError(ValueError):
    """Raised when a file looks like time-series data, which is out of scope."""


def _timestamp_like_columns(df: pd.DataFrame) -> list[str]:
    cols = []
    for c in df.columns:
        name = str(c).lower()
        if any(tok in name for tok in _TIME_TOKENS):
            cols.append(c)
    return cols


def is_longitudinal(df: pd.DataFrame, subject_key: str | None) -> bool:
    """True if the same subject repeats AND a timestamp-like column exists."""
    if subject_key is None or subject_key not in df.columns:
        return False
    repeats = df[subject_key].duplicated().any()
    return bool(repeats and _timestamp_like_columns(df))


def reject_if_longitudinal(df: pd.DataFrame, subject_key: str | None, name: str) -> None:
    if is_longitudinal(df, subject_key):
        ts = _timestamp_like_columns(df)
        raise LongitudinalInputError(
            f"{name}: looks longitudinal (repeated {subject_key} + time columns {ts}). "
            "Time-series data is out of scope for schema v0.1; do not aggregate to fit."
        )
