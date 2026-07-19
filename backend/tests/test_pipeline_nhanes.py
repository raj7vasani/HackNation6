"""End-to-end pipeline test on the NHANES P_RHQ sample (heuristic mode)."""

from __future__ import annotations

import pandas as pd
import pytest

from pcos_harmonizer.config import DATA_DIR
from pcos_harmonizer.pipeline import run_from_mapping, run_pipeline

XPT = DATA_DIR / "P_RHQ.xpt"
pytestmark = pytest.mark.skipif(not XPT.exists(), reason="data/P_RHQ.xpt not present")


def test_pipeline_runs(tmp_path):
    res = run_pipeline(
        [XPT],
        client=None,  # offline heuristic
        source="nhanes",
        mapping_out=tmp_path / "mapping.yaml",
        output_path=tmp_path / "out.csv",
    )
    assert not res.table.empty
    assert "subject_id" in res.table.columns
    assert res.coverage["verdict"]
    assert (tmp_path / "mapping.yaml").exists()
    assert res.output_path and res.output_path.exists()
    # Coverage should honestly report limited reproductive-only data.
    assert res.coverage["n_criteria_evaluable"] <= 3


def test_deterministic_rerun(tmp_path):
    r1 = run_pipeline([XPT], client=None, mapping_out=tmp_path / "m.yaml")
    r2 = run_from_mapping([XPT], tmp_path / "m.yaml")
    pd.testing.assert_frame_equal(
        r1.table.reset_index(drop=True), r2.table.reset_index(drop=True)
    )
