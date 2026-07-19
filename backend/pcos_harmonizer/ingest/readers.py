"""Read raw inputs (CSV / TSV / XPT / XLSX) into DataFrames + column labels."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd


@dataclass
class IngestedFile:
    """A single loaded source file."""

    name: str
    df: pd.DataFrame
    labels: dict[str, str] = field(default_factory=dict)  # column → variable label
    path: Path | None = None


def read_file(path: str | Path) -> IngestedFile:
    """Read one file by extension. XPT carries variable labels; others usually don't."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Input file not found: {path}")

    suffix = path.suffix.lower()
    labels: dict[str, str] = {}

    if suffix == ".xpt":
        try:
            import pyreadstat

            df, meta = pyreadstat.read_xport(str(path))
            raw = getattr(meta, "column_names_to_labels", None) or {}
            labels = {k: v for k, v in raw.items() if v}
        except Exception:
            df = pd.read_sas(path, format="xport")
    elif suffix in (".csv",):
        df = pd.read_csv(path)
    elif suffix in (".tsv", ".tab"):
        df = pd.read_csv(path, sep="\t")
    elif suffix in (".xlsx", ".xls"):
        df = pd.read_excel(path)
    else:
        raise ValueError(
            f"Unsupported input extension {suffix!r} for {path.name}. "
            "Supported: .xpt, .csv, .tsv, .xlsx, .xls"
        )

    return IngestedFile(name=path.name, df=df, labels=labels, path=path)


def read_files(paths) -> list[IngestedFile]:
    return [read_file(p) for p in paths]
