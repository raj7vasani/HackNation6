"""Criterion-flag derivations (spec §7). Guard clauses first: suppression →
``not_applicable``, not ``false``. No biochemical threshold is hardcoded — the
schema deliberately stores no reference range, so biochemical hyperandrogenism is
only asserted from source-supplied flags."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from ..transform.missingness import NOT_APPLICABLE, UNKNOWN, is_missing_code

_BOOL_TYPES = (bool, np.bool_)


def _bool(value: Any) -> bool | None:
    if isinstance(value, _BOOL_TYPES):
        return bool(value)
    if value is None or is_missing_code(value):
        return None
    if isinstance(value, str):
        low = value.strip().lower()
        if low in ("true", "1", "yes"):
            return True
        if low in ("false", "0", "no"):
            return False
    return None


def _num(value: Any) -> float | None:
    if value is None or is_missing_code(value) or isinstance(value, _BOOL_TYPES):
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return None if pd.isna(f) else f


def _suppressed(row) -> bool:
    if _bool(row.get("hysterectomy_flag")):
        return True
    if str(row.get("pregnancy_status")).lower() == "pregnant":
        return True
    if str(row.get("hormonal_contraceptive_use")).lower() == "current":
        return True
    return False


def _ovulatory(row) -> Any:
    if _bool(row.get("hysterectomy_flag")) or str(row.get("pregnancy_status")).lower() == "pregnant":
        return NOT_APPLICABLE
    if _bool(row.get("amenorrhea_flag")) or _bool(row.get("oligomenorrhea_flag")):
        return True
    if _bool(row.get("irregular_cycles_self_report")):
        return True
    cpy = _num(row.get("cycles_per_year"))
    if cpy is not None and cpy < 8:
        return True
    clen = _num(row.get("cycle_length_days_typical"))
    if clen is not None and (clen < 21 or clen > 35):
        return True
    # We had cycle data and none indicated dysfunction.
    if any(
        _num(row.get(f)) is not None or _bool(row.get(f)) is not None
        for f in ("cycles_per_year", "cycle_length_days_typical", "amenorrhea_flag", "oligomenorrhea_flag")
    ):
        return False
    return UNKNOWN


def _hyperandrogenism(row) -> Any:
    if str(row.get("hormonal_contraceptive_use")).lower() == "current":
        return NOT_APPLICABLE  # SHBG elevation makes androgen indices uninterpretable
    if _bool(row.get("androgenic_medication")):
        return NOT_APPLICABLE
    if _bool(row.get("hirsutism_flag")):
        return True
    return UNKNOWN


def _pcom(row) -> Any:
    threshold = row.get("pcom_threshold_applied")
    if threshold is None or is_missing_code(threshold) or not str(threshold).strip():
        # Never set pcom without a documented threshold.
        return row.get("pcom_flag", UNKNOWN)
    src = _bool(row.get("pcom_flag"))
    if src is not None:
        return src
    return UNKNOWN


def derive_criteria(df: pd.DataFrame) -> list[str]:
    """Add criterion-flag columns in place. Returns notes/warnings."""
    warnings: list[str] = []
    ovul, hyper, pcom = [], [], []
    for _, row in df.iterrows():
        ovul.append(_ovulatory(row))
        hyper.append(_hyperandrogenism(row))
        pcom.append(_pcom(row))
    df["ovulatory_dysfunction_derived"] = ovul
    df["hyperandrogenism_derived"] = hyper
    df["pcom_flag"] = pcom
    return warnings
