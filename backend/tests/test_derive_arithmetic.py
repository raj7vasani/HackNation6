"""Tests for arithmetic derivations."""

from __future__ import annotations

import math

import pandas as pd

from pcos_harmonizer.derive.arithmetic import derive_arithmetic
from pcos_harmonizer.transform.missingness import NOT_MEASURED


def test_bmi():
    df = pd.DataFrame({"weight_kg": [70.0], "height_cm": [175.0]})
    derive_arithmetic(df)
    assert math.isclose(df["bmi"].iloc[0], 70 / (1.75**2), rel_tol=1e-6)


def test_homa_ir_with_pmol_insulin():
    # 6.945 pmol/L == 1 µIU/mL; HOMA-IR = glucose * insulin_uIU / 22.5
    df = pd.DataFrame({"fasting_glucose": [5.0], "fasting_insulin": [6.945]})
    derive_arithmetic(df, insulin_unit="pmol/L")
    assert math.isclose(df["homa_ir"].iloc[0], 5.0 * 1.0 / 22.5, rel_tol=1e-3)


def test_afc_and_volume_max():
    df = pd.DataFrame(
        {
            "antral_follicle_count_left": [10],
            "antral_follicle_count_right": [15],
            "ovarian_volume_left_ml": [8.0],
            "ovarian_volume_right_ml": [12.0],
        }
    )
    derive_arithmetic(df)
    assert df["antral_follicle_count_max"].iloc[0] == 15
    assert df["ovarian_volume_max_ml"].iloc[0] == 12.0


def test_missing_inputs_skip():
    df = pd.DataFrame({"weight_kg": [NOT_MEASURED], "height_cm": [175.0]})
    derive_arithmetic(df)
    assert df["bmi"].iloc[0] is None
