"""Tests for value standardization (heuristic path)."""

from __future__ import annotations

from pcos_harmonizer.propose.value_mapper import propose_value_map
from pcos_harmonizer.schema.loader import get_registry


def test_boolean_value_map():
    f = get_registry().get("hysterectomy_flag")
    vm = propose_value_map(f, [1, 2])
    assert vm["1"] is True
    assert vm["2"] is False


def test_enum_value_map_blocks_unknown():
    f = get_registry().get("hormonal_contraceptive_use")
    vm = propose_value_map(f, ["current", "never", "???"])
    assert vm["current"] == "current"
    assert vm["never"] == "never"
    assert "???" not in vm  # unmapped raw value is blocked, not guessed


def test_numeric_field_returns_none():
    assert propose_value_map(get_registry().get("age_years"), [20, 30]) is None


def test_verbatim_field_returns_none():
    assert propose_value_map(get_registry().get("race_ethnicity"), ["White", "Black"]) is None
