"""Coverage report (IMPLEMENTATION_NOTES §8) — the "money output".

Per-criterion full / partial / absent, critical confounder status, and the
verdict from ``x_coverage_report.verdict_rule``. "Cannot support a Rotterdam
diagnosis" is a valid, useful result — it is not softened.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from ..schema.registry import FieldRegistry
from ..transform.missingness import is_missing_code

# Direct/measured evaluable fields per criterion (a populated one → "full").
_MEASURED = {
    "criterion_1": ("progesterone_luteal", "cycle_length_days_typical", "cycles_per_year"),
    "criterion_2": ("total_testosterone", "free_testosterone", "free_androgen_index", "dheas", "androstenedione"),
    "criterion_3": ("antral_follicle_count_max", "ovarian_volume_max_ml", "amh"),
}


def _populated_count(df: pd.DataFrame, fieldname: str) -> int:
    if fieldname not in df.columns:
        return 0
    return int(sum(_present(v) for v in df[fieldname]))


def _present(value: Any) -> bool:
    if value is None or is_missing_code(value):
        return False
    if isinstance(value, float) and pd.isna(value):
        return False
    if isinstance(value, str) and not value.strip():
        return False
    return True


def _criterion_status(df: pd.DataFrame, evaluable: list[str], measured: tuple[str, ...]) -> str:
    any_measured = any(_populated_count(df, f) > 0 for f in measured)
    any_evaluable = any(_populated_count(df, f) > 0 for f in evaluable)
    if any_measured:
        return "full"
    if any_evaluable:
        return "partial"
    return "absent"


def coverage_report(
    df: pd.DataFrame, registry: FieldRegistry, provenance: dict[str, Any] | None = None
) -> dict[str, Any]:
    cfg = registry.coverage_config
    n_subjects = len(df)

    criteria = {}
    for i, key in enumerate(("criterion_1", "criterion_2", "criterion_3"), start=1):
        evaluable = cfg.get(f"{key}_evaluable", [])
        status = _criterion_status(df, evaluable, _MEASURED[key])
        populated = {f: _populated_count(df, f) for f in evaluable}
        criteria[key] = {
            "status": status,
            "evaluable_fields": evaluable,
            "populated": {f: c for f, c in populated.items() if c > 0},
        }

    n_evaluable = sum(1 for c in criteria.values() if c["status"] != "absent")

    confounders = {}
    for cf in cfg.get("critical_confounders", []):
        confounders[cf] = _populated_count(df, cf)
    exclusions_populated = _populated_count(df, "exclusions_assessed_flag") > 0

    can_support = n_evaluable >= 2 and exclusions_populated
    verdict = (
        "Can support a Rotterdam diagnosis"
        if can_support
        else "Cannot support a Rotterdam diagnosis"
    )
    reasons = []
    if n_evaluable < 2:
        reasons.append(f"only {n_evaluable}/3 criteria evaluable (need ≥2)")
    if not exclusions_populated:
        reasons.append("exclusions_assessed_flag not populated")

    return {
        "n_subjects": n_subjects,
        "criteria": criteria,
        "n_criteria_evaluable": n_evaluable,
        "critical_confounders": confounders,
        "exclusions_assessed": exclusions_populated,
        "verdict": verdict,
        "verdict_reasons": reasons,
        "verdict_rule": cfg.get("verdict_rule"),
    }


def format_report(report: dict[str, Any]) -> str:
    """Human-readable summary."""
    lines = [
        "PCOS Coverage Report",
        "=" * 40,
        f"Subjects: {report['n_subjects']}",
        f"Criteria evaluable: {report['n_criteria_evaluable']}/3",
        "",
    ]
    labels = {
        "criterion_1": "Ovulatory dysfunction",
        "criterion_2": "Hyperandrogenism",
        "criterion_3": "Polycystic ovarian morphology",
    }
    for key, label in labels.items():
        c = report["criteria"][key]
        lines.append(f"  [{c['status'].upper():7}] {label}")
        for f, n in c["populated"].items():
            lines.append(f"            - {f}: {n} populated")
    lines.append("")
    lines.append("Critical confounders:")
    for cf, n in report["critical_confounders"].items():
        lines.append(f"  - {cf}: {'present' if n else 'MISSING'}")
    lines.append(f"  - exclusions_assessed_flag: {'present' if report['exclusions_assessed'] else 'MISSING'}")
    lines.append("")
    lines.append(f"VERDICT: {report['verdict']}")
    for r in report["verdict_reasons"]:
        lines.append(f"  - {r}")
    return "\n".join(lines)
