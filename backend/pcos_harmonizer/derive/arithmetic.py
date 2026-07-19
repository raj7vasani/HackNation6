"""Arithmetic derivations (spec §7). Computed only when all inputs are present in
canonical units; never overwrites a source-supplied value (disagreement warns)."""

from __future__ import annotations

from typing import Any

import pandas as pd

from ..transform.missingness import is_missing_code

TOLERANCE = 0.05  # relative tolerance for source-vs-derived disagreement


def _num(value: Any) -> float | None:
    if value is None or is_missing_code(value):
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return None if pd.isna(f) else f


def _insulin_uiu(value: float | None, canonical_unit: str | None) -> float | None:
    """HOMA-IR needs insulin in µIU/mL; canonical storage may be pmol/L."""
    if value is None:
        return None
    if canonical_unit == "pmol/L":
        return value / 6.945
    return value


def _apply(df: pd.DataFrame, target: str, fn, warnings: list[str]) -> None:
    """Compute ``target`` row-wise via ``fn(row)``; keep source value if present."""
    computed = [fn(row) for _, row in df.iterrows()]
    if target in df.columns:
        for i, (existing, comp) in enumerate(zip(df[target], computed)):
            ev, cv = _num(existing), _num(comp)
            if ev is None and cv is not None:
                df.at[df.index[i], target] = cv
            elif ev is not None and cv is not None and abs(ev - cv) > TOLERANCE * max(abs(ev), 1e-9):
                warnings.append(
                    f"{target}: source {ev:.4g} vs derived {cv:.4g} disagree (row {i})"
                )
    else:
        df[target] = computed


def derive_arithmetic(df: pd.DataFrame, insulin_unit: str | None = "pmol/L") -> list[str]:
    """Add derived arithmetic columns in place. Returns disagreement warnings."""
    warnings: list[str] = []

    def bmi(r):
        w, h = _num(r.get("weight_kg")), _num(r.get("height_cm"))
        return w / (h / 100) ** 2 if w and h else None

    def whr(r):
        wa, hi = _num(r.get("waist_circumference_cm")), _num(r.get("hip_circumference_cm"))
        return wa / hi if wa and hi else None

    def fai(r):
        t, s = _num(r.get("total_testosterone")), _num(r.get("shbg"))
        return 100 * t / s if t is not None and s else None

    def homa(r):
        g = _num(r.get("fasting_glucose"))
        ins = _insulin_uiu(_num(r.get("fasting_insulin")), insulin_unit)
        return g * ins / 22.5 if g is not None and ins is not None else None

    def lhfsh(r):
        lh, fsh = _num(r.get("lh")), _num(r.get("fsh"))
        return lh / fsh if lh is not None and fsh else None

    def afc_max(r):
        vals = [_num(r.get("antral_follicle_count_left")), _num(r.get("antral_follicle_count_right"))]
        vals = [v for v in vals if v is not None]
        return max(vals) if vals else None

    def ov_max(r):
        vals = [_num(r.get("ovarian_volume_left_ml")), _num(r.get("ovarian_volume_right_ml"))]
        vals = [v for v in vals if v is not None]
        return max(vals) if vals else None

    _apply(df, "bmi", bmi, warnings)
    _apply(df, "waist_hip_ratio", whr, warnings)
    _apply(df, "free_androgen_index", fai, warnings)
    _apply(df, "homa_ir", homa, warnings)
    _apply(df, "lh_fsh_ratio", lhfsh, warnings)
    _apply(df, "antral_follicle_count_max", afc_max, warnings)
    _apply(df, "ovarian_volume_max_ml", ov_max, warnings)
    return warnings
