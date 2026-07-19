"""Validator — runs the schema's ``x_validator_rules`` as warnings (spec §6/§7).

Out-of-range and consistency issues are *warnings*, not hard failures: an
out-of-range value often means an unconverted unit, which a reviewer should see.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from ..schema.registry import FieldRegistry
from ..transform.missingness import NOT_APPLICABLE, is_missing_code

_CYCLE_FIELDS = (
    "cycle_length_days_typical",
    "cycles_per_year",
    "oligomenorrhea_flag",
    "amenorrhea_flag",
    "irregular_cycles_self_report",
)
_ANDROGEN_FIELDS = (
    "total_testosterone",
    "free_testosterone",
    "free_androgen_index",
    "dheas",
    "androstenedione",
)
_SCORE_INSTRUMENT = {
    "depression_screen_score": "depression_instrument",
    "anxiety_screen_score": "anxiety_instrument",
    "quality_of_life_score": "quality_of_life_instrument",
}


@dataclass
class Warning:
    rule: str
    message: str
    severity: str = "warning"  # warning | critical
    subject: Any = None

    def to_dict(self) -> dict[str, Any]:
        return {"rule": self.rule, "message": self.message, "severity": self.severity, "subject": self.subject}


def _present(value: Any) -> bool:
    if value is None or is_missing_code(value):
        return False
    if isinstance(value, float) and pd.isna(value):
        return False
    if isinstance(value, str) and not value.strip():
        return False
    return True


def _num(value: Any) -> float | None:
    if not _present(value):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def validate(df: pd.DataFrame, registry: FieldRegistry) -> list[dict[str, Any]]:
    """Return a list of warning dicts."""
    warnings: list[Warning] = []
    cols = set(df.columns)

    for i, row in df.iterrows():
        sid = row.get("subject_id", i)

        # pcom_flag requires pcom_threshold_applied
        if _present(row.get("pcom_flag")) and not _present(row.get("pcom_threshold_applied")):
            warnings.append(Warning("pcom_threshold_required",
                "pcom_flag present without pcom_threshold_applied", subject=sid))

        # adolescent PCOM window
        age = _num(row.get("age_years"))
        if age is not None and age < 20:
            cm = row.get("criteria_met")
            if isinstance(cm, (list, tuple)) and "pcom" in cm:
                warnings.append(Warning("adolescent_pcom",
                    "PCOM is not a valid criterion within ~8 years of menarche (age<20)",
                    subject=sid))

        # hysterectomy → cycle fields not_applicable
        if row.get("hysterectomy_flag") in (True, "true", "True"):
            for f in _CYCLE_FIELDS:
                if f in cols and _present(row.get(f)) and row.get(f) != NOT_APPLICABLE:
                    warnings.append(Warning("hysterectomy_cycle_na",
                        f"{f} should be not_applicable when hysterectomy_flag is true", subject=sid))

        # current hormonal contraception → suppression warning
        hc = str(row.get("hormonal_contraceptive_use")).lower()
        if hc == "current":
            warnings.append(Warning("oc_suppression",
                "hormonal_contraceptive_use=current: androgen/cycle fields carry a suppression caveat",
                subject=sid))
            if str(row.get("contraceptive_type")).lower() == "combined_oral":
                warnings.append(Warning("oc_fai_uninterpretable",
                    "combined_oral + current: SHBG elevation makes free_androgen_index uninterpretable",
                    severity="critical", subject=sid))
        if hc in ("never", "none"):
            ct = str(row.get("contraceptive_type")).lower()
            if ct not in ("none", "non_hormonal", "nan", "") and _present(row.get("contraceptive_type")):
                warnings.append(Warning("contraceptive_type_conflict",
                    f"hormonal_contraceptive_use={hc} but contraceptive_type={ct}", subject=sid))

        # androgen value present but assay method missing → critical
        if any(_present(row.get(f)) for f in _ANDROGEN_FIELDS if f in cols):
            if "androgen_assay_method" not in cols or not _present(row.get("androgen_assay_method")):
                warnings.append(Warning("androgen_assay_missing",
                    "androgen value present but androgen_assay_method missing",
                    severity="critical", subject=sid))

        # score requires instrument
        for score, instrument in _SCORE_INSTRUMENT.items():
            if score in cols and _present(row.get(score)):
                if instrument not in cols or not _present(row.get(instrument)):
                    warnings.append(Warning("score_instrument_missing",
                        f"{score} present without {instrument}", subject=sid))

        # diagnosis unknown, not false, without exclusions
        diag = row.get("pcos_diagnosis_flag")
        if diag is False and row.get("exclusions_assessed_flag") not in (True, "true", "True"):
            warnings.append(Warning("diagnosis_needs_exclusions",
                "pcos_diagnosis_flag is false without exclusions_assessed_flag; should be 'unknown'",
                subject=sid))

        # x_range plausibility
        for fname in cols:
            fld = registry.get(fname)
            if fld is None or fld.x_range is None:
                continue
            v = _num(row.get(fname))
            if v is None:
                continue
            lo, hi = fld.x_range
            if v < lo or v > hi:
                warnings.append(Warning("out_of_range",
                    f"{fname}={v:g} outside plausible range [{lo}, {hi}] (possible unit issue)",
                    subject=sid))

    return [w.to_dict() for w in warnings]
