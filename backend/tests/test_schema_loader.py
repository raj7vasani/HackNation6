"""Tests for the schema loader / field registry."""

from __future__ import annotations

from pcos_harmonizer.schema.loader import get_registry


def test_registry_loads_fields():
    reg = get_registry()
    assert len(reg) > 50
    assert "_provenance" not in reg.names()


def test_numeric_field():
    f = get_registry().get("age_at_menarche")
    assert f is not None
    assert f.is_numeric
    assert f.unit == "years"
    assert "RHQ010" in f.hints


def test_enum_field():
    f = get_registry().get("hormonal_contraceptive_use")
    assert f.is_enum
    assert f.enum is not None and "current" in f.enum


def test_boolean_field():
    assert get_registry().get("hysterectomy_flag").is_boolean


def test_verbatim_field():
    assert get_registry().get("race_ethnicity").preserve_verbatim


def test_derivable_and_groups():
    reg = get_registry()
    assert any(f.name == "bmi" for f in reg.derivable_fields())
    assert reg.fields_in_group("demographics")
    assert reg.critical_fields()


def test_conversions_oracle_present():
    conv = get_registry().conversions()
    assert "total_testosterone" in conv
