"""Shared helpers and codebook labels for NHANES Reproductive Health (P_RHQ).

Source: https://wwwn.cdc.gov/Nchs/Data/Nhanes/Public/2017/DataFiles/P_RHQ.htm
Cycle: 2017–March 2020 pre-pandemic.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

# NHANES special codes treated as non-substantive responses
REFUSED_CODES = {7, 77, 777, 7777}
DONT_KNOW_CODES = {9, 99, 999, 9999}
SPECIAL_CODES = REFUSED_CODES | DONT_KNOW_CODES

VARIABLE_LABELS: dict[str, str] = {
    "SEQN": "Respondent sequence number",
    "RHQ010": "Age at first menstrual period (years)",
    "RHD018": "Estimated age at menarche (months)",
    "RHQ020": "Age range at first menstrual period",
    "RHQ031": "Had ≥1 menstrual period in past 12 months",
    "RHD043": "Reason for no period in past 12 months",
    "RHQ060": "Age at last menstrual period (years)",
    "RHQ070": "Age range at last menstrual period",
    "RHQ074": "Tried ≥1 year to become pregnant",
    "RHQ076": "Saw doctor because unable to become pregnant",
    "RHQ078": "Ever treated for pelvic infection / PID",
    "RHQ131": "Ever been pregnant",
    "RHD143": "Currently pregnant",
    "RHQ160": "Number of pregnancies",
    "RHQ162": "Gestational diabetes during pregnancy",
    "RHD167": "Total number of deliveries",
    "RHQ171": "Deliveries resulting in live birth",
    "RHQ172": "Any baby ≥9 lbs at birth",
    "RHD180": "Age at first live birth",
    "RHD190": "Age at last live birth",
    "RHQ197": "Months since last baby",
    "RHQ200": "Currently breastfeeding",
    "RHD280": "Had a hysterectomy",
    "RHQ305": "Had both ovaries removed",
    "RHQ332": "Age when both ovaries removed",
    "RHQ540": "Ever used female hormones (excl. birth control)",
    "RHQ542A": "Hormone pills used",
    "RHQ542B": "Hormone patches used",
    "RHQ542C": "Hormone cream/suppository/injection used",
    "RHQ542D": "Other form of female hormone used",
    "RHQ554": "Used estrogen-only hormone pills",
    "RHQ570": "Used estrogen/progestin combo pills",
}

# Value maps for key categoricals (PCOS / menstrual-history relevant)
VALUE_LABELS: dict[str, dict[float, str]] = {
    "RHQ031": {1: "Yes", 2: "No", 7: "Refused", 9: "Don't know"},
    "RHD043": {
        1: "Pregnancy",
        2: "Breast feeding",
        3: "Hysterectomy",
        7: "Menopause",
        9: "Other",
        77: "Refused",
        99: "Don't know",
    },
    "RHQ074": {1: "Yes", 2: "No", 7: "Refused", 9: "Don't know"},
    "RHQ076": {1: "Yes", 2: "No", 7: "Refused", 9: "Don't know"},
    "RHQ078": {1: "Yes", 2: "No", 7: "Refused", 9: "Don't know"},
    "RHQ131": {1: "Yes", 2: "No", 7: "Refused", 9: "Don't know"},
    "RHD143": {1: "Yes", 2: "No", 7: "Refused", 9: "Don't know"},
    "RHQ162": {
        1: "Yes",
        2: "No",
        3: "Borderline",
        7: "Refused",
        9: "Don't know",
    },
    "RHD280": {1: "Yes", 2: "No", 7: "Refused", 9: "Don't know"},
    "RHQ305": {1: "Yes", 2: "No", 7: "Refused", 9: "Don't know"},
    "RHQ540": {1: "Yes", 2: "No", 7: "Refused", 9: "Don't know"},
}

# Fields most relevant to oligo/anovulation / fertility (Rotterdam-adjacent)
PCOS_RELEVANT = [
    "RHQ010",  # menarche age
    "RHQ031",  # period in last 12 months (amenorrhea proxy, not cycle regularity)
    "RHD043",  # reason for amenorrhea — "Other" may include PCOS
    "RHQ074",  # infertility attempt
    "RHQ076",  # infertility care
    "RHQ162",  # gestational diabetes (metabolic comorbidity)
]


def load_xpt(path: Path | str) -> pd.DataFrame:
    """Read a SAS XPORT (.xpt) file into a DataFrame."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"XPT file not found: {path}")

    try:
        import pyreadstat

        df, _meta = pyreadstat.read_xport(str(path))
    except Exception:
        df = pd.read_sas(path, format="xport")

    # SEQN is an integer ID
    if "SEQN" in df.columns:
        df["SEQN"] = df["SEQN"].astype("Int64")
    return df


def is_special_code(series: pd.Series) -> pd.Series:
    """Mask refused / don't-know codes (exact match after rounding)."""
    rounded = series.round()
    return rounded.isin(SPECIAL_CODES)


def clean_numeric(series: pd.Series, *, treat_zero_as_missing: bool = False) -> pd.Series:
    """Replace NHANES special codes with NaN; optionally treat 0 as missing."""
    out = series.copy()
    out = out.mask(is_special_code(out))
    # SAS sometimes encodes missing as near-zero floats
    out = out.mask(out.abs() < 1e-10)
    if treat_zero_as_missing:
        out = out.mask(out == 0)
    return out


def labeled_counts(df: pd.DataFrame, column: str) -> pd.Series:
    """Value counts with codebook labels when available."""
    labels = VALUE_LABELS.get(column, {})
    counts = df[column].value_counts(dropna=False).sort_index()
    if not labels:
        return counts
    index = [
        labels.get(float(i), f"{i} (unlabeled)") if pd.notna(i) else "Missing"
        for i in counts.index
    ]
    counts.index = index
    return counts


def column_profile(df: pd.DataFrame) -> pd.DataFrame:
    """Per-column missingness and basic type summary."""
    rows = []
    n = len(df)
    for col in df.columns:
        s = df[col]
        special = int(is_special_code(s).sum()) if pd.api.types.is_numeric_dtype(s) else 0
        missing = int(s.isna().sum())
        rows.append(
            {
                "column": col,
                "label": VARIABLE_LABELS.get(col, ""),
                "non_null": n - missing,
                "missing": missing,
                "missing_pct": round(100 * missing / n, 2),
                "special_codes": special,
                "nunique": int(s.nunique(dropna=True)),
                "dtype": str(s.dtype),
            }
        )
    return pd.DataFrame(rows)
