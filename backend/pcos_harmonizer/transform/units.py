"""Unit conversion — pint + molar mass + a short specials list (IMPLEMENTATION_NOTES §2).

Do **not** hand-write a pairwise factor table. Three layers:

1. ``pint`` for dimensional units (lb→kg, in→cm).
2. Molar mass per analyte for mass↔substance (ng/dL → nmol/L).
3. A short specials list for IU-based / affine / composition-dependent cases.

The LLM never runs here; this is deterministic. Callers decide when to *block*
(unknown unit); this module raises :class:`CannotConvert` when it cannot.
"""

from __future__ import annotations

from typing import Any

import pint

_UREG = pint.UnitRegistry()

# --- Layer 2: molar masses (g/mol) -----------------------------------------
MOLAR_MASS_G_PER_MOL: dict[str, float] = {
    "total_testosterone": 288.42,
    "free_testosterone": 288.42,
    "estradiol": 272.38,
    "progesterone_luteal": 314.46,
    "androstenedione": 286.41,
    "dheas": 368.49,
    "cortisol": 362.46,
    "17_hydroxyprogesterone": 330.46,
    "fasting_glucose": 180.16,
    "ogtt_2hr_glucose": 180.16,
    "total_cholesterol": 386.65,
    "hdl_cholesterol": 386.65,
    "ldl_cholesterol": 386.65,
}

# --- Layer 3: specials ------------------------------------------------------
# IU-based or composition-dependent: no clean molar route. from_unit → factor.
SPECIAL_LINEAR: dict[str, dict[str, float]] = {
    "fasting_insulin": {"uIU/mL": 6.945, "mIU/L": 6.945},
    "prolactin": {"ng/mL": 21.2},
    "triglycerides": {"mg/dL": 0.0113},
    "amh": {"ng/mL": 7.14},  # ~140 kDa glycoprotein; not a clean molar mass
}

# Affine (not multiplicative). field → {from_unit: callable}
SPECIAL_AFFINE: dict[str, dict[str, Any]] = {
    "hba1c_percent": {"mmol/mol (IFCC)": lambda x: x * 0.0915 + 2.15},
}

# Raw unit token → pint-parseable name.
_UNIT_ALIASES = {
    "in": "inch",
    "lb": "pound",
    "cm": "centimeter",
    "kg": "kilogram",
    "mL": "milliliter",
    "ug/dL": "microgram/deciliter",
    "µg/dL": "microgram/deciliter",
    "umol/L": "micromole/liter",
    "µmol/L": "micromole/liter",
    "ng/dL": "nanogram/deciliter",
    "ng/mL": "nanogram/milliliter",
    "pg/mL": "picogram/milliliter",
    "nmol/L": "nanomole/liter",
    "pmol/L": "picomole/liter",
    "mmol/L": "millimole/liter",
    "mg/dL": "milligram/deciliter",
}

_MASS_VOL = _UREG("gram/liter").dimensionality
_SUBST_VOL = _UREG("mole/liter").dimensionality


class CannotConvert(ValueError):
    """Raised when no conversion route exists for the given units/field."""


def _norm(unit: str) -> str:
    return _UNIT_ALIASES.get(unit.strip(), unit.strip())


def _pint(unit: str):
    return _UREG(_norm(unit))


def convert(value: float, from_unit: str | None, to_unit: str | None, field: str | None = None):
    """Return ``(converted_value, description)`` or raise :class:`CannotConvert`.

    ``description`` is a human-readable ``transformation_applied`` string.
    """
    if from_unit is None or to_unit is None:
        raise CannotConvert("unit unknown (from or to is None)")

    if from_unit == to_unit or _norm(from_unit) == _norm(to_unit):
        return value, f"{from_unit} (no conversion)"

    # Layer 3a — affine specials
    if field and field in SPECIAL_AFFINE and from_unit in SPECIAL_AFFINE[field]:
        out = SPECIAL_AFFINE[field][from_unit](value)
        return out, f"{from_unit} -> {to_unit} (affine, {field})"

    # Layer 3b — linear specials
    if field and field in SPECIAL_LINEAR and from_unit in SPECIAL_LINEAR[field]:
        factor = SPECIAL_LINEAR[field][from_unit]
        return value * factor, f"{from_unit} -> {to_unit} (special x{factor})"

    # Layer 2 — molar
    if field and field in MOLAR_MASS_G_PER_MOL:
        try:
            return _molar(value, from_unit, to_unit, MOLAR_MASS_G_PER_MOL[field])
        except pint.PintError:
            pass

    # Layer 1 — physical
    try:
        out = _pint(from_unit).__mul__(value).to(_norm(to_unit)).magnitude  # type: ignore[union-attr]
    except pint.PintError as exc:
        raise CannotConvert(
            f"no conversion route {from_unit!r} -> {to_unit!r} for field {field!r}"
        ) from exc
    return out, f"{from_unit} -> {to_unit} (pint)"


def _molar(value: float, from_unit: str, to_unit: str, mw: float):
    q = value * _pint(from_unit)
    mm = mw * _UREG("g/mol")
    tgt = _pint(to_unit)
    if q.dimensionality == _MASS_VOL and tgt.dimensionality == _SUBST_VOL:
        out = (q / mm).to(_norm(to_unit)).magnitude
    elif q.dimensionality == _SUBST_VOL and tgt.dimensionality == _MASS_VOL:
        out = (q * mm).to(_norm(to_unit)).magnitude
    else:
        out = q.to(_norm(to_unit)).magnitude
    return out, f"{from_unit} -> {to_unit} (molar, MW {mw})"


def conversion_factor(field: str | None, from_unit: str, to_unit: str) -> float:
    """Multiplicative factor for 1.0 unit (test oracle vs. x_conversions)."""
    out, _desc = convert(1.0, from_unit, to_unit, field)
    return out
