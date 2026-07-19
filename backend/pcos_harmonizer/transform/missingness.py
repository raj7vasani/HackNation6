"""Typed missingness (spec §6) and source sentinel decoding (IMPLEMENTATION_NOTES §5)."""

from __future__ import annotations

from typing import Any

import pandas as pd

# spec §6 — missing values are never blank.
NOT_MEASURED = "not_measured"
BELOW_LOD = "below_lod"
NOT_APPLICABLE = "not_applicable"
WITHHELD = "withheld"
UNKNOWN = "unknown"

MISSING_CODES = {NOT_MEASURED, BELOW_LOD, NOT_APPLICABLE, WITHHELD, UNKNOWN}


def is_missing_code(value: Any) -> bool:
    return isinstance(value, str) and value in MISSING_CODES


def decode_sentinel(value: Any, sentinel_map: dict[Any, str] | None) -> Any:
    """Map a raw sentinel value to a typed missing code, else pass through.

    ``sentinel_map`` keys may be ints or strings (YAML loads them as ints);
    matching is done on both the raw value and its stringified form.
    """
    if sentinel_map is None or value is None:
        return value
    if pd.isna(value):
        return NOT_MEASURED
    if value in sentinel_map:
        return sentinel_map[value]
    # numeric floats read from XPT (e.g. 999.0) — compare as int and str
    try:
        as_int = int(value)
        if as_int in sentinel_map:
            return sentinel_map[as_int]
        if str(as_int) in sentinel_map:
            return sentinel_map[str(as_int)]
    except (TypeError, ValueError):
        pass
    if str(value) in sentinel_map:
        return sentinel_map[str(value)]
    return value


def code_missing(value: Any) -> Any:
    """Replace a bare NaN/None with ``not_measured``; leave codes/values intact."""
    if value is None or (not isinstance(value, str) and pd.isna(value)):
        return NOT_MEASURED
    return value


def normalize_value_key(value: Any) -> str:
    """Canonical string key for value_map lookups.

    XPT reads integer codes as floats (``1.0``), so a value_map keyed ``"1"`` must
    still match. Integer-valued numbers (and strings like ``"1.0"``) normalize to
    ``"1"``; everything else falls back to ``str(value)``.
    """
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, (int, float)):
        try:
            f = float(value)
            if f.is_integer():
                return str(int(f))
        except (TypeError, ValueError, OverflowError):
            pass
        return str(value)
    s = str(value)
    try:
        f = float(s)
        if f.is_integer():
            return str(int(f))
    except (TypeError, ValueError):
        pass
    return s
