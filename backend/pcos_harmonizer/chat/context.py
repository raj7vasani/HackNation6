"""Build the text context the data-chat assistant reasons over.

The goal is a *compact* but information-dense snapshot of a pipeline run — small
enough to sit in the model's context on every turn, rich enough to answer real
questions about the data. We never dump the full table (it can be thousands of
rows); we summarize it: shape, coverage verdict, column mapping, per-column
statistics, missingness breakdown, warnings, and a handful of sample rows.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pandas as pd

from ..report.coverage import format_report
from ..transform.missingness import is_missing_code

if TYPE_CHECKING:  # avoid a heavy import at module load
    from ..pipeline import PipelineResult

# Keep the context bounded regardless of dataset size.
MAX_COLUMNS_DETAILED = 60
MAX_SAMPLE_ROWS = 5
MAX_CATEGORY_LEVELS = 8


def _present_mask(series: pd.Series) -> pd.Series:
    """True where a value is a real observation (not a missingness code / NaN)."""
    def ok(v: Any) -> bool:
        if v is None or is_missing_code(v):
            return False
        if isinstance(v, float) and pd.isna(v):
            return False
        if isinstance(v, str) and not v.strip():
            return False
        return True

    return series.map(ok)


def _missingness_breakdown(series: pd.Series) -> dict[str, int]:
    """Count each missingness code present in a column."""
    counts: dict[str, int] = {}
    for v in series:
        if isinstance(v, str) and is_missing_code(v):
            counts[v] = counts.get(v, 0) + 1
        elif v is None or (isinstance(v, float) and pd.isna(v)):
            counts["<null>"] = counts.get("<null>", 0) + 1
    return counts


def _column_summary(series: pd.Series, n_rows: int) -> str:
    present = series[_present_mask(series)]
    n_present = int(len(present))
    pct = (100.0 * n_present / n_rows) if n_rows else 0.0
    parts = [f"present {n_present}/{n_rows} ({pct:.0f}%)"]

    # Try to treat the present values as numeric.
    numeric = pd.to_numeric(present, errors="coerce")
    numeric = numeric.dropna()
    if n_present and len(numeric) >= 0.8 * n_present:
        if len(numeric):
            parts.append(
                f"min {numeric.min():.4g}, median {numeric.median():.4g}, "
                f"mean {numeric.mean():.4g}, max {numeric.max():.4g}"
            )
    else:
        # Categorical / enum column — show the top levels.
        vc = present.astype(str).value_counts().head(MAX_CATEGORY_LEVELS)
        levels = ", ".join(f"{val}={cnt}" for val, cnt in vc.items())
        if levels:
            parts.append(f"values: {levels}")

    miss = _missingness_breakdown(series)
    if miss:
        parts.append("missing: " + ", ".join(f"{k}={v}" for k, v in miss.items()))

    return "; ".join(parts)


def _table_profile(df: pd.DataFrame) -> str:
    n_rows = len(df)
    cols = list(df.columns)
    lines = [f"Standardized table: {n_rows} rows × {len(cols)} columns."]
    shown = cols[:MAX_COLUMNS_DETAILED]
    for col in shown:
        lines.append(f"  - {col}: {_column_summary(df[col], n_rows)}")
    if len(cols) > len(shown):
        lines.append(f"  … and {len(cols) - len(shown)} more columns (ask to see them).")
    return "\n".join(lines)


def _mapping_summary(result: "PipelineResult") -> str:
    mapping = result.mapping
    lines = ["Column mapping (source → canonical):"]
    active = [m for m in mapping.mappings if m.canonical_field]
    for m in active:
        unit = ""
        if m.unit_raw or m.unit_canonical:
            unit = f" [{m.unit_raw or '?'} → {m.unit_canonical or '?'}]"
        conf = f" conf={m.mapping_confidence:.2f}" if m.mapping_confidence is not None else ""
        lines.append(
            f"  - {m.source_column} → {m.canonical_field}{unit}"
            f" (source={m.source}{conf}, reviewed={m.human_reviewed})"
        )
    if mapping.unmapped_columns:
        names = ", ".join(u.source_column for u in mapping.unmapped_columns)
        lines.append(f"  Unmapped (not guessed): {names}")
    if mapping.blocked:
        names = ", ".join(b.source_column for b in mapping.blocked)
        lines.append(f"  Blocked pending unit review: {names}")
    return "\n".join(lines)


def _warnings_summary(result: "PipelineResult") -> str:
    if not result.warnings:
        return "Validator warnings: none."
    by_rule: dict[str, int] = {}
    for w in result.warnings:
        rule = w.get("rule", "?") if isinstance(w, dict) else "?"
        by_rule[rule] = by_rule.get(rule, 0) + 1
    top = sorted(by_rule.items(), key=lambda kv: -kv[1])
    body = ", ".join(f"{rule}={n}" for rule, n in top)
    return f"Validator warnings ({len(result.warnings)} total): {body}"


def _sample_rows(df: pd.DataFrame) -> str:
    if df.empty:
        return "Sample rows: (table is empty)."
    sample = df.head(MAX_SAMPLE_ROWS)
    # Keep it narrow: cap columns so the CSV stays readable in context.
    cols = list(df.columns)[:MAX_COLUMNS_DETAILED]
    csv = sample[cols].to_csv(index=False)
    return f"First {len(sample)} rows (first {len(cols)} columns), CSV:\n{csv}"


def build_data_context(result: "PipelineResult") -> str:
    """Serialize a :class:`PipelineResult` into the assistant's grounding context."""
    blocks = [
        ("COVERAGE REPORT", format_report(result.coverage)),
        ("COLUMN MAPPING", _mapping_summary(result)),
        ("COLUMN STATISTICS", _table_profile(result.table)),
        ("VALIDATOR WARNINGS", _warnings_summary(result)),
        ("SAMPLE ROWS", _sample_rows(result.table)),
    ]
    return "\n\n".join(f"=== {title} ===\n{body}" for title, body in blocks)
