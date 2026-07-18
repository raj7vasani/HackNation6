#!/usr/bin/env python3
"""Extract NHANES .xpt reproductive-health data to CSV and a column profile.

Example:
  python scripts/extract_xpt.py data/P_RHQ.xpt
  python scripts/extract_xpt.py /Users/you/Downloads/P_RHQ.xpt -o outputs
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow running as `python scripts/extract_xpt.py` without installing a package
sys.path.insert(0, str(Path(__file__).resolve().parent))

from nhanes_rhq import VARIABLE_LABELS, column_profile, load_xpt  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "xpt_path",
        type=Path,
        nargs="?",
        default=Path("data/P_RHQ.xpt"),
        help="Path to the .xpt file (default: data/P_RHQ.xpt)",
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        type=Path,
        default=Path("outputs"),
        help="Directory for CSV outputs (default: outputs/)",
    )
    args = parser.parse_args()

    df = load_xpt(args.xpt_path)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    stem = args.xpt_path.stem
    csv_path = args.output_dir / f"{stem}.csv"
    profile_path = args.output_dir / f"{stem}_profile.csv"
    dict_path = args.output_dir / f"{stem}_data_dictionary.csv"

    df.to_csv(csv_path, index=False)
    profile = column_profile(df)
    profile.to_csv(profile_path, index=False)

    dictionary = profile[["column", "label", "missing_pct", "nunique"]].copy()
    dictionary.to_csv(dict_path, index=False)

    print(f"Loaded {args.xpt_path}")
    print(f"  rows × cols : {df.shape[0]:,} × {df.shape[1]}")
    print(f"  wrote       : {csv_path}")
    print(f"  wrote       : {profile_path}")
    print(f"  wrote       : {dict_path}")
    print()
    print("Columns:")
    for col in df.columns:
        label = VARIABLE_LABELS.get(col, "")
        print(f"  {col:10s}  {label}")


if __name__ == "__main__":
    main()
