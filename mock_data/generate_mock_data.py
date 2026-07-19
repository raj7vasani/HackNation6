"""Generate synthetic .xpt mock inputs for testing the PCOS harmonizer.

These files are *not* real patient data. They mimic the shape of research
exports (SAS XPORT with variable labels, mixed units, categorical codes and
NHANES-style missing sentinels) so the LLM propose step and the deterministic
transform/derive/report path can be exercised end to end.

Run:  python mock_data/generate_mock_data.py
Deps: pandas, numpy, pyreadstat
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pyreadstat

HERE = Path(__file__).resolve().parent
RNG = np.random.default_rng(42)


def _write(df: pd.DataFrame, labels: dict[str, str], filename: str) -> None:
    path = HERE / filename
    column_labels = [labels.get(c, "") for c in df.columns]
    pyreadstat.write_xport(df, str(path), column_labels=column_labels)
    print(f"wrote {path}  ({df.shape[0]} rows x {df.shape[1]} cols)")


def make_clinic(n: int = 40) -> None:
    """A rich fertility-clinic style cohort spanning all 3 Rotterdam criteria.

    Column names deliberately differ from the schema field names / NHANES codes so
    the LLM must map from the human-readable labels. Weight/height are in imperial
    units to exercise unit conversion.
    """
    df = pd.DataFrame(
        {
            "PATID": np.arange(1001, 1001 + n),
            "AGE": RNG.integers(19, 42, n).astype(float),
            "MENARCHE": np.round(RNG.normal(12.6, 1.3, n), 1),
            "CYCLEN": RNG.choice([28, 30, 35, 45, 60, 90], n, p=[0.25, 0.2, 0.15, 0.15, 0.15, 0.1]).astype(float),
            "CYCYR": RNG.choice([12, 11, 9, 6, 4, 3], n, p=[0.3, 0.2, 0.15, 0.15, 0.1, 0.1]).astype(float),
            "IRREG": RNG.choice([1, 2], n, p=[0.55, 0.45]),
            "TESTO": np.round(RNG.normal(55, 22, n), 1),  # ng/dL
            "SHBG": np.round(RNG.normal(45, 18, n), 1),  # nmol/L
            "ANDRASSY": ["lcmsms"] * n,
            "HIRSUT": RNG.choice([1, 2], n, p=[0.45, 0.55]),
            "GLU": np.round(RNG.normal(95, 14, n), 0),  # mg/dL
            "INS": np.round(RNG.normal(13, 6, n), 1),  # uIU/mL
            "WT": np.round(RNG.normal(172, 34, n), 1),  # lb
            "HT": np.round(RNG.normal(64.5, 2.6, n), 1),  # in
            "WAIST": np.round(RNG.normal(92, 14, n), 1),  # cm
            "HIP": np.round(RNG.normal(104, 13, n), 1),  # cm
            "OCUSE": RNG.choice(["never", "former", "current"], n, p=[0.55, 0.3, 0.15]),
            "PREG": RNG.choice([1, 2], n, p=[0.05, 0.95]),
            "HYSTER": RNG.choice([1, 2], n, p=[0.05, 0.95]),
            "AFCL": RNG.integers(4, 26, n).astype(float),
            "AFCR": RNG.integers(4, 26, n).astype(float),
            "OVL": np.round(RNG.normal(9.5, 3.5, n), 1),
            "OVR": np.round(RNG.normal(9.8, 3.5, n), 1),
            "AMH": np.round(RNG.normal(4.5, 2.6, n), 2),  # ng/mL
            "PCOMTHR": ["AFC>=12"] * n,
            "EXCLASSD": RNG.choice([1, 2], n, p=[0.7, 0.3]),
        }
    )

    labels = {
        "PATID": "Participant identifier",
        "AGE": "Age in years at examination",
        "MENARCHE": "Age in years when first menstrual period occurred",
        "CYCLEN": "Typical menstrual cycle length (days)",
        "CYCYR": "Number of menstrual periods in the last 12 months",
        "IRREG": "Self-reported irregular menstrual cycles (1=yes, 2=no)",
        "TESTO": "Total testosterone, serum (ng/dL)",
        "SHBG": "Sex hormone binding globulin (nmol/L)",
        "ANDRASSY": "Testosterone assay method (immunoassay or lcmsms)",
        "HIRSUT": "Clinician-assessed hirsutism present (1=yes, 2=no)",
        "GLU": "Fasting plasma glucose (mg/dL)",
        "INS": "Fasting serum insulin (uIU/mL)",
        "WT": "Body weight (lb)",
        "HT": "Standing height (in)",
        "WAIST": "Waist circumference (cm)",
        "HIP": "Hip circumference (cm)",
        "OCUSE": "Hormonal contraceptive use status (current, former, never)",
        "PREG": "Currently pregnant (1=yes, 2=no)",
        "HYSTER": "History of hysterectomy (1=yes, 2=no)",
        "AFCL": "Antral follicle count, left ovary",
        "AFCR": "Antral follicle count, right ovary",
        "OVL": "Ovarian volume, left ovary (mL)",
        "OVR": "Ovarian volume, right ovary (mL)",
        "AMH": "Anti-Mullerian hormone (ng/mL)",
        "PCOMTHR": "Ultrasound polycystic morphology threshold applied",
        "EXCLASSD": "Exclusion conditions (thyroid, prolactin, CAH) assessed (1=yes, 2=no)",
    }
    _write(df, labels, "mock_pcos_clinic.xpt")


def make_nhanes_repro(n: int = 30) -> None:
    """A reproductive-health-only NHANES-style file (coverage should be limited).

    Uses real NHANES variable codes and 4/1-digit missing sentinels.
    """
    menarche = np.round(RNG.normal(12.7, 1.4, n), 0)
    menarche[RNG.choice(n, 3, replace=False)] = 7777  # refused
    menarche[RNG.choice(n, 2, replace=False)] = 9999  # don't know

    irreg = RNG.choice([1, 2], n, p=[0.4, 0.6]).astype(float)
    irreg[RNG.choice(n, 2, replace=False)] = 9  # don't know

    df = pd.DataFrame(
        {
            "SEQN": np.arange(90001, 90001 + n).astype(float),
            "RIDAGEYR": RNG.integers(18, 55, n).astype(float),
            "RHQ010": menarche,
            "RHQ031": irreg,
            "RHD143": RNG.choice([1.0, 2.0], n, p=[0.06, 0.94]),
            "RHD280": RNG.choice([1.0, 2.0, 9.0], n, p=[0.08, 0.9, 0.02]),
        }
    )
    labels = {
        "SEQN": "Respondent sequence number",
        "RIDAGEYR": "Age in years at screening",
        "RHQ010": "Age in years when first menstrual period occurred",
        "RHQ031": "Regular periods in the past 12 months (1=yes, 2=no)",
        "RHD143": "Currently pregnant (1=yes, 2=no)",
        "RHD280": "Ever had a hysterectomy (1=yes, 2=no)",
    }
    _write(df, labels, "mock_nhanes_repro.xpt")


if __name__ == "__main__":
    make_clinic()
    make_nhanes_repro()
    print("done.")
