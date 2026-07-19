"""Tests for sentinel decoding and typed missingness."""

from __future__ import annotations

import numpy as np

from pcos_harmonizer.transform import missingness as m


def test_sentinel_int_and_float():
    assert m.decode_sentinel(7, {7: m.WITHHELD}) == m.WITHHELD
    assert m.decode_sentinel(999.0, {999: m.UNKNOWN}) == m.UNKNOWN


def test_raw_7_is_not_value_7():
    # A sentinel 7 must never be treated as the numeric value 7.
    assert m.decode_sentinel(7, {7: m.WITHHELD}) != 7


def test_real_value_passes_through():
    assert m.decode_sentinel(12, {7: m.WITHHELD}) == 12


def test_nan_becomes_not_measured():
    assert m.decode_sentinel(np.nan, {7: m.WITHHELD}) == m.NOT_MEASURED


def test_code_missing():
    assert m.code_missing(None) == m.NOT_MEASURED
    assert m.code_missing(5) == 5
    assert m.is_missing_code(m.WITHHELD)
    assert not m.is_missing_code(5)
