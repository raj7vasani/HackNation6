"""Tests for the interactive review helpers (pause-for-input flow)."""

from __future__ import annotations

import pytest

from pcos_harmonizer import app_api, review
from pcos_harmonizer.config import MOCK_DATA_DIR

MOCK_XPT = MOCK_DATA_DIR / "mock_pcos_clinic.xpt"

pytestmark = pytest.mark.skipif(not MOCK_XPT.exists(), reason="mock clinic file not present")


@pytest.fixture
def proposal():
    # Offline heuristic propose → a mapping with blocked columns to review.
    return app_api.propose_for_review([MOCK_XPT], engine="heuristic", source="nhanes")


def test_propose_surfaces_blocked_columns(proposal):
    assert proposal.engine_used == "heuristic"
    blocked = review.pending_units(proposal.mapping)
    assert blocked, "expected some columns blocked on unknown units"
    # Every blocked column maps to a numeric field with a canonical unit but no unit_raw.
    for b in blocked:
        entry = review.entry_for(proposal.mapping, b.source_column)
        assert entry is not None
        assert entry.unit_canonical is not None
        assert entry.unit_raw is None


def test_unit_options_puts_canonical_first():
    assert review.unit_options("nmol/L")[0] == "nmol/L"
    assert "ng/dL" in review.unit_options("nmol/L")
    # Unknown canonical unit falls back to just itself.
    assert review.unit_options("score") == ["score"]
    assert review.unit_options(None) == []


def test_apply_unit_answers_resolves_and_marks_reviewed(proposal):
    mapping = proposal.mapping
    blocked = review.pending_units(mapping)
    target = blocked[0].source_column
    n_before = len(mapping.blocked)

    review.apply_unit_answers(mapping, {target: "ng/dL"})

    entry = review.entry_for(mapping, target)
    assert entry.unit_raw == "ng/dL"
    assert entry.human_reviewed is True
    assert len(mapping.blocked) == n_before - 1
    assert all(b.source_column != target for b in mapping.blocked)


def test_empty_answer_leaves_column_blocked(proposal):
    mapping = proposal.mapping
    n_before = len(mapping.blocked)
    review.apply_unit_answers(mapping, {mapping.blocked[0].source_column: ""})
    assert len(mapping.blocked) == n_before  # empty answer = unresolved


def test_answer_applies_to_duplicate_columns_across_files():
    """The same column name in several files resolves from one answer."""
    from pcos_harmonizer.mapping.model import BlockedColumn, MappingEntry, MappingFile

    mapping = MappingFile(
        mappings=[
            MappingEntry(source_file="A.xpt", source_column="WTSAF2YR",
                         canonical_field="weight_kg", unit_canonical="kg"),
            MappingEntry(source_file="B.xpt", source_column="WTSAF2YR",
                         canonical_field="weight_kg", unit_canonical="kg"),
        ],
        blocked=[
            BlockedColumn(source_file="A.xpt", source_column="WTSAF2YR", reason="unit_raw_unknown"),
            BlockedColumn(source_file="B.xpt", source_column="WTSAF2YR", reason="unit_raw_unknown"),
        ],
    )

    review.apply_unit_answers(mapping, {"WTSAF2YR": "lb"})

    assert all(e.unit_raw == "lb" and e.human_reviewed for e in mapping.mappings)
    assert mapping.blocked == []  # both duplicate entries cleared


def test_full_interactive_roundtrip_produces_result(proposal):
    mapping = proposal.mapping
    # Answer one testosterone-ish column if present; otherwise any blocked one.
    blocked = review.pending_units(mapping)
    target = next(
        (b.source_column for b in blocked
         if (e := review.entry_for(mapping, b.source_column)) and e.unit_canonical == "nmol/L"),
        blocked[0].source_column,
    )
    entry = review.entry_for(mapping, target)
    review.apply_unit_answers(mapping, {target: review.unit_options(entry.unit_canonical)[-1]})

    outcome = app_api.complete_after_review(
        [MOCK_XPT], mapping, engine_used=proposal.engine_used, source="nhanes"
    )
    assert outcome.result.table.shape[0] > 0
    assert "verdict" in outcome.result.coverage
