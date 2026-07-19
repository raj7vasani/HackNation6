"""Diagnosis derivations (spec §7): criteria_met → phenotype → pcos_diagnosis_flag.

Rotterdam = ≥2 of 3 criteria. A positive label requires exclusions to be assessed;
otherwise the flag is ``unknown`` (validator rule), never ``false``."""

from __future__ import annotations

from typing import Any

import numpy as np

from ..transform.missingness import UNKNOWN, is_missing_code

_BOOL_TYPES = (bool, np.bool_)

# Phenotype = which criteria are met (spec §7 / schema x_derivable).
_PHENOTYPE = {
    frozenset({"ovulatory", "hyperandrogenism", "pcom"}): "A",
    frozenset({"ovulatory", "hyperandrogenism"}): "B",
    frozenset({"hyperandrogenism", "pcom"}): "C",
    frozenset({"ovulatory", "pcom"}): "D",
}


def _true(value: Any) -> bool:
    if isinstance(value, _BOOL_TYPES):
        return bool(value)
    return isinstance(value, str) and value.strip().lower() in ("true", "1", "yes")


def _bool_or_none(value: Any) -> bool | None:
    if isinstance(value, _BOOL_TYPES):
        return bool(value)
    if value is None or is_missing_code(value):
        return None
    if isinstance(value, str) and value.strip().lower() in ("true", "false"):
        return value.strip().lower() == "true"
    return None


def derive_diagnosis(df: pd.DataFrame) -> list[str]:
    """Add criteria_met, phenotype, pcos_diagnosis_flag in place. Returns warnings."""
    warnings: list[str] = []
    criteria_met, phenotype, diagnosis = [], [], []

    for _, row in df.iterrows():
        met = []
        if _true(row.get("ovulatory_dysfunction_derived")):
            met.append("ovulatory")
        if _true(row.get("hyperandrogenism_derived")):
            met.append("hyperandrogenism")
        if _true(row.get("pcom_flag")):
            met.append("pcom")
        criteria_met.append(met)
        phenotype.append(_PHENOTYPE.get(frozenset(met), "unknown" if len(met) < 2 else "unknown"))

        exclusions = _bool_or_none(row.get("exclusions_assessed_flag"))
        src = _bool_or_none(row.get("pcos_diagnosis_flag"))
        if src is not None:
            derived = src  # never overwrite a source-supplied diagnosis
        elif len(met) >= 2:
            derived = True if exclusions is True else UNKNOWN
        else:
            # Cannot assert PCOS; without full evaluability, prefer unknown over false.
            derived = UNKNOWN
        diagnosis.append(derived)

    df["criteria_met"] = criteria_met
    df["phenotype"] = phenotype
    df["pcos_diagnosis_flag"] = diagnosis
    return warnings
