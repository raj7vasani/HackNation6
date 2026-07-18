#!/usr/bin/env python3
"""Exploratory analysis of NHANES P_RHQ for PCOS-adjacent reproductive variables.

Focuses on menstrual history, amenorrhea reasons, infertility, and gestational
diabetes — fields that map toward Rotterdam oligo/anovulation and related
covariates. Note: RHQ031 measures presence of ≥1 period in 12 months, not
cycle-length regularity.

Example:
  python scripts/analyze_rhq.py data/P_RHQ.xpt
  python scripts/analyze_rhq.py data/P_RHQ.xpt --no-plots
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from nhanes_rhq import (  # noqa: E402
    PCOS_RELEVANT,
    VARIABLE_LABELS,
    clean_numeric,
    labeled_counts,
    load_xpt,
)


def _print_section(title: str) -> None:
    print()
    print("=" * 72)
    print(title)
    print("=" * 72)


def summarize_overview(df: pd.DataFrame) -> None:
    _print_section("Dataset overview")
    print(f"Respondents (female, 12+): {len(df):,}")
    print(f"Variables:                 {df.shape[1]}")
    print(f"Unique SEQN:               {df['SEQN'].nunique():,}")


def summarize_menarche(df: pd.DataFrame) -> pd.Series:
    _print_section("Menarche age (RHQ010) — early menarche is a PCOS-relevant covariate")
    age = clean_numeric(df["RHQ010"], treat_zero_as_missing=True)
    # Cap at biologically plausible soft-edit range used by NHANES (≈8–25)
    age = age.where((age >= 6) & (age <= 25))
    stats = age.describe(percentiles=[0.1, 0.25, 0.5, 0.75, 0.9])
    print(stats.to_string())
    early = (age < 12).sum()
    print(f"\nEarly menarche (<12y): {early:,} / {age.notna().sum():,} "
          f"({100 * early / age.notna().sum():.1f}%)")
    return age


def summarize_amenorrhea(df: pd.DataFrame) -> None:
    _print_section(
        "Period in past 12 months (RHQ031) + reason if none (RHD043)\n"
        "  Note: RHQ031 is amenorrhea/presence, NOT cycle regularity."
    )
    print("\nRHQ031 — Had ≥1 menstrual period in past 12 months:")
    print(labeled_counts(df, "RHQ031").to_string())

    print("\nRHD043 — Reason for no period (among those answering):")
    print(labeled_counts(df, "RHD043").to_string())

    # "Other" amenorrhea reasons are the closest RHQ proxy for possible PCOS
    reason = df["RHD043"]
    answered = reason.notna().sum()
    other = (reason == 9).sum()
    if answered:
        print(
            f"\n'Other' amenorrhea reason: {other:,} / {answered:,} "
            f"({100 * other / answered:.1f}% of amenorrhea reasons) — "
            "may include PCOS and other causes."
        )


def summarize_fertility(df: pd.DataFrame) -> None:
    _print_section("Infertility markers (RHQ074 / RHQ076)")
    for col in ("RHQ074", "RHQ076"):
        print(f"\n{col} — {VARIABLE_LABELS[col]}:")
        print(labeled_counts(df, col).to_string())

    # Among those who tried ≥1 year, how many saw a doctor?
    tried = df["RHQ074"] == 1
    saw_dr = df.loc[tried, "RHQ076"]
    if tried.any():
        yes = (saw_dr == 1).sum()
        print(
            f"\nAmong those who tried ≥1 year without pregnancy: "
            f"{yes:,} / {tried.sum():,} ({100 * yes / tried.sum():.1f}%) "
            "saw a doctor."
        )


def summarize_gdm(df: pd.DataFrame) -> None:
    _print_section("Gestational diabetes (RHQ162) — metabolic comorbidity")
    print(labeled_counts(df, "RHQ162").to_string())


def summarize_pcos_proxy_table(df: pd.DataFrame, out_dir: Path) -> pd.DataFrame:
    """Build a compact table of PCOS-adjacent flags for downstream mapping."""
    _print_section("PCOS-adjacent derived flags (unweighted)")

    menarche = clean_numeric(df["RHQ010"], treat_zero_as_missing=True)
    menarche = menarche.where((menarche >= 6) & (menarche <= 25))

    table = pd.DataFrame(
        {
            "SEQN": df["SEQN"],
            "age_menarche_years": menarche,
            "early_menarche": menarche < 12,
            "period_in_last_12mo": df["RHQ031"].map({1: True, 2: False}),
            "amenorrhea_reason": df["RHD043"].map(
                {
                    1: "pregnancy",
                    2: "breastfeeding",
                    3: "hysterectomy",
                    7: "menopause",
                    9: "other",
                }
            ),
            "amenorrhea_other": df["RHD043"] == 9,
            "infertility_tried_1yr": df["RHQ074"].map({1: True, 2: False}),
            "infertility_saw_doctor": df["RHQ076"].map({1: True, 2: False}),
            "gestational_diabetes": df["RHQ162"].map(
                {1: "yes", 2: "no", 3: "borderline"}
            ),
        }
    )

    flag_cols = [
        "early_menarche",
        "amenorrhea_other",
        "infertility_tried_1yr",
        "infertility_saw_doctor",
    ]
    for col in flag_cols:
        n = table[col].notna().sum()
        if n == 0:
            continue
        rate = 100 * table[col].fillna(False).sum() / len(table)
        print(f"  {col:28s}  prevalence (all rows): {rate:5.1f}%")

    path = out_dir / "P_RHQ_pcos_proxy_flags.csv"
    table.to_csv(path, index=False)
    print(f"\nWrote derived flags → {path}")
    return table


def make_plots(df: pd.DataFrame, menarche: pd.Series, out_dir: Path) -> None:
    _print_section("Saving plots")
    fig_dir = out_dir / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)

    # 1. Menarche age histogram
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.hist(menarche.dropna(), bins=np.arange(6.5, 26.5, 1), edgecolor="white")
    ax.set_xlabel("Age at first menstrual period (years)")
    ax.set_ylabel("Count")
    ax.set_title("NHANES P_RHQ — Age at menarche")
    ax.axvline(12, color="crimson", linestyle="--", linewidth=1.2, label="Early menarche <12")
    ax.legend()
    fig.tight_layout()
    p1 = fig_dir / "menarche_age_hist.png"
    fig.savefig(p1, dpi=140)
    plt.close(fig)
    print(f"  {p1}")

    # 2. Amenorrhea reasons bar chart
    reason_counts = labeled_counts(df, "RHD043")
    reason_counts = reason_counts[reason_counts.index != "Missing"]
    fig, ax = plt.subplots(figsize=(8, 4.5))
    reason_counts.plot(kind="barh", ax=ax, color="#2a6f7a")
    ax.set_xlabel("Count")
    ax.set_title("Reason for no period in past 12 months (RHD043)")
    fig.tight_layout()
    p2 = fig_dir / "amenorrhea_reasons.png"
    fig.savefig(p2, dpi=140)
    plt.close(fig)
    print(f"  {p2}")

    # 3. Missingness for PCOS-relevant columns
    miss = df[PCOS_RELEVANT].isna().mean().sort_values(ascending=True) * 100
    labels = [f"{c}\n{VARIABLE_LABELS.get(c, '')[:40]}" for c in miss.index]
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.barh(labels, miss.values, color="#c45c26")
    ax.set_xlabel("Missing (%)")
    ax.set_title("Missingness — PCOS-adjacent RHQ fields")
    fig.tight_layout()
    p3 = fig_dir / "pcos_fields_missingness.png"
    fig.savefig(p3, dpi=140)
    plt.close(fig)
    print(f"  {p3}")


def write_summary_report(
    df: pd.DataFrame,
    menarche: pd.Series,
    out_dir: Path,
) -> Path:
    period_yes = int((df["RHQ031"] == 1).sum())
    period_no = int((df["RHQ031"] == 2).sum())
    other_amen = int((df["RHD043"] == 9).sum())
    infertility = int((df["RHQ074"] == 1).sum())
    gdm = int((df["RHQ162"] == 1).sum())

    report = out_dir / "P_RHQ_analysis_summary.md"
    report.write_text(
        f"""# NHANES P_RHQ analysis summary

**Source:** Reproductive Health questionnaire, 2017–March 2020 pre-pandemic  
**Docs:** https://wwwn.cdc.gov/Nchs/Data/Nhanes/Public/2017/DataFiles/P_RHQ.htm

## Scale

| Metric | Value |
| --- | --- |
| Respondents | {len(df):,} |
| Variables | {df.shape[1]} |

## PCOS-adjacent findings (unweighted)

| Signal | Count / note |
| --- | --- |
| Median age at menarche | {menarche.median():.0f} years (n={menarche.notna().sum():,}) |
| Early menarche (<12) | {(menarche < 12).sum():,} ({100 * (menarche < 12).sum() / menarche.notna().sum():.1f}%) |
| ≥1 period in last 12 mo | Yes {period_yes:,} / No {period_no:,} |
| Amenorrhea reason = Other | {other_amen:,} (possible PCOS among other causes) |
| Tried ≥1 yr to conceive | {infertility:,} |
| Gestational diabetes (yes) | {gdm:,} |

## Schema-mapping notes

- `RHQ031` is **not** cycle regularity; it asks whether any period occurred in 12 months.
- True oligo/anovulation for Rotterdam mapping is **not directly coded** in P_RHQ.
- Closest proxies: amenorrhea with reason `Other` (`RHD043=9`), infertility (`RHQ074`/`RHQ076`), early menarche (`RHQ010`).
- Hormone labs (testosterone, SHBG) live in separate NHANES files and must be joined on `SEQN`.
""",
        encoding="utf-8",
    )
    print(f"\nWrote summary → {report}")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "xpt_path",
        type=Path,
        nargs="?",
        default=Path("data/P_RHQ.xpt"),
        help="Path to P_RHQ.xpt (default: data/P_RHQ.xpt)",
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        type=Path,
        default=Path("outputs"),
        help="Output directory (default: outputs/)",
    )
    parser.add_argument(
        "--no-plots",
        action="store_true",
        help="Skip writing figure PNGs",
    )
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    df = load_xpt(args.xpt_path)

    summarize_overview(df)
    menarche = summarize_menarche(df)
    summarize_amenorrhea(df)
    summarize_fertility(df)
    summarize_gdm(df)
    summarize_pcos_proxy_table(df, args.output_dir)

    if not args.no_plots:
        make_plots(df, menarche, args.output_dir)

    write_summary_report(df, menarche, args.output_dir)
    print("\nDone.")


if __name__ == "__main__":
    main()
