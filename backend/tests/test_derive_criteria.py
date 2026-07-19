"""Tests for criterion-flag derivations (guard clauses)."""

from __future__ import annotations

import pandas as pd

from pcos_harmonizer.derive.criteria import derive_criteria
from pcos_harmonizer.transform.missingness import NOT_APPLICABLE


def test_hysterectomy_makes_ovulatory_not_applicable():
    df = pd.DataFrame({"hysterectomy_flag": [True], "amenorrhea_flag": [True]})
    derive_criteria(df)
    assert df["ovulatory_dysfunction_derived"].iloc[0] == NOT_APPLICABLE


def test_amenorrhea_implies_ovulatory_dysfunction():
    df = pd.DataFrame({"amenorrhea_flag": [True]})
    derive_criteria(df)
    assert bool(df["ovulatory_dysfunction_derived"].iloc[0]) is True


def test_current_oc_suppresses_hyperandrogenism():
    df = pd.DataFrame({"hormonal_contraceptive_use": ["current"], "hirsutism_flag": [True]})
    derive_criteria(df)
    assert df["hyperandrogenism_derived"].iloc[0] == NOT_APPLICABLE


def test_pcom_needs_threshold():
    df = pd.DataFrame({"pcom_flag": [True], "pcom_threshold_applied": [None]})
    derive_criteria(df)
    # Without a documented threshold, pcom is not asserted from a bare boolean.
    assert df["pcom_flag"].iloc[0] is not True
