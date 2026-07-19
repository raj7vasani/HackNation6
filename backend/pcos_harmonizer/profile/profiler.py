"""Per-column profiling (pipeline step [2]).

Produces the compact signal the proposer needs: the column name (question id),
its label (question text), and lightweight stats. Row data is never sent to the
LLM — only this profile.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from ..ingest.readers import IngestedFile

# Suffixes that hint at a unit embedded in the column name.
_UNIT_SUFFIX_RE = re.compile(
    r"_(ng_?dl|ng_?ml|pg_?ml|nmol_?l|pmol_?l|mg_?dl|mmol_?l|umol_?l|ug_?dl|"
    r"iu_?l|miu_?l|uiu_?ml|kg|cm|mm|ml|lb|in|years?|days?|months?)$",
    re.IGNORECASE,
)
# Units mentioned in a label, e.g. "Fasting Glucose (mg/dL)" or "Weight (lb)".
_KNOWN_UNITS = (
    r"ng/dL|ng/mL|pg/mL|nmol/L|pmol/L|mg/dL|mmol/L|umol/L|µmol/L|ug/dL|µg/dL|"
    r"mIU/L|IU/L|uIU/mL|kg/m2|kg|lb|cm|mm|mL|in|inches|years?|yrs?|days?|months?|"
    r"%|mmHg|score|ratio|count"
)
_UNIT_PAREN_RE = re.compile(rf"\(\s*({_KNOWN_UNITS})\s*\)", re.IGNORECASE)


@dataclass
class ColumnProfile:
    source_file: str
    source_column: str  # question id
    label: str | None  # question text
    dtype: str
    n_unique: int
    null_rate: float
    min: float | None = None
    max: float | None = None
    samples: list[Any] = field(default_factory=list)
    unit_signals: list[str] = field(default_factory=list)

    def to_llm_input(self) -> dict[str, Any]:
        """Minimal per-column payload: id + question (team decision)."""
        return {"question_id": self.source_column, "question": self.label or ""}


def _unit_signals(column: str, label: str | None) -> list[str]:
    signals: list[str] = []
    m = _UNIT_SUFFIX_RE.search(str(column))
    if m:
        signals.append(f"name_suffix:{m.group(1)}")
    if label:
        for m in _UNIT_PAREN_RE.finditer(label):
            signals.append(f"label_unit:{m.group(1).strip()}")
    return signals


def profile_column(
    series: pd.Series, source_file: str, column: str, label: str | None, n_samples: int = 8
) -> ColumnProfile:
    non_null = series.dropna()
    vmin = vmax = None
    if pd.api.types.is_numeric_dtype(series) and not non_null.empty:
        vmin = float(non_null.min())
        vmax = float(non_null.max())
    samples = non_null.unique().tolist()[:n_samples]
    return ColumnProfile(
        source_file=source_file,
        source_column=str(column),
        label=label or None,
        dtype=str(series.dtype),
        n_unique=int(series.nunique(dropna=True)),
        null_rate=float(series.isna().mean()),
        min=vmin,
        max=vmax,
        samples=samples,
        unit_signals=_unit_signals(column, label),
    )


def profile_file(ingested: IngestedFile, n_samples: int = 8) -> list[ColumnProfile]:
    profiles = []
    for col in ingested.df.columns:
        profiles.append(
            profile_column(
                ingested.df[col],
                ingested.name,
                col,
                ingested.labels.get(col),
                n_samples=n_samples,
            )
        )
    return profiles
