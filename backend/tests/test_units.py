"""Unit converter tested against the schema's x_conversions oracle (±1%)."""

from __future__ import annotations

import math

import pytest

from pcos_harmonizer.schema.loader import get_registry
from pcos_harmonizer.transform.units import CannotConvert, conversion_factor, convert


def test_conversion_oracle():
    reg = get_registry()
    checked = 0
    for field_name, conv in reg.conversions().items():
        field = reg.get(field_name)
        if field is None or field.unit is None:
            continue
        for from_unit, factor in conv.items():
            if not isinstance(factor, (int, float)):
                continue  # affine formulas (e.g. hba1c) handled separately
            got = conversion_factor(field_name, from_unit, field.unit)
            assert math.isclose(got, factor, rel_tol=0.01), (
                f"{field_name}: {from_unit}->{field.unit} got {got}, expected {factor}"
            )
            checked += 1
    assert checked > 10


def test_identity_no_conversion():
    val, desc = convert(5.0, "nmol/L", "nmol/L", "total_testosterone")
    assert val == 5.0
    assert "no conversion" in desc


def test_physical_pint():
    val, _ = convert(1.0, "in", "cm", "height_cm")
    assert math.isclose(val, 2.54, rel_tol=1e-6)


def test_hba1c_affine():
    val, _ = convert(50.0, "mmol/mol (IFCC)", "% (NGSP)", "hba1c_percent")
    assert math.isclose(val, 50 * 0.0915 + 2.15, rel_tol=1e-9)


def test_unknown_unit_blocks():
    with pytest.raises(CannotConvert):
        convert(1.0, None, "kg", "weight_kg")
    with pytest.raises(CannotConvert):
        convert(1.0, "furlong", "kg", "weight_kg")
