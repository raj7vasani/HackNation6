"""Tests for the multi-format output writer."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pandas as pd
import pytest

from pcos_harmonizer import output


@pytest.fixture
def df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "subject_id": ["A1", "A2"],
            "age_at_menarche": [12.0, 13.0],
            "amenorrhea_flag": [True, False],
        }
    )


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("csv", "csv"),
        (".CSV", "csv"),
        ("excel", "xlsx"),
        ("dta", "stata"),
        ("xport", "xpt"),
        ("ndjson", "jsonl"),
    ],
)
def test_normalize_format(raw, expected):
    assert output.normalize_format(raw) == expected


def test_normalize_format_rejects_unknown():
    with pytest.raises(output.UnsupportedFormatError):
        output.normalize_format("docx")


def test_infer_format_from_extension():
    assert output.infer_format("out/standardized.parquet") == "parquet"
    assert output.infer_format(Path("x.dta")) == "stata"


def test_infer_format_unknown_extension():
    with pytest.raises(output.UnsupportedFormatError):
        output.infer_format("mystery.bin")


def test_csv_roundtrip(df):
    data = output.to_bytes(df, "csv")
    back = pd.read_csv(io.BytesIO(data))
    assert list(back.columns) == list(df.columns)
    assert len(back) == 2


def test_json_records(df):
    data = output.to_bytes(df, "json")
    records = json.loads(data)
    assert records[0]["subject_id"] == "A1"
    assert records[0]["age_at_menarche"] == 12.0


def test_jsonl_lines(df):
    data = output.to_bytes(df, "jsonl").decode()
    lines = [ln for ln in data.splitlines() if ln.strip()]
    assert len(lines) == 2
    assert json.loads(lines[0])["subject_id"] == "A1"


def test_write_output_infers_and_writes(tmp_path, df):
    dest = tmp_path / "standardized.csv"
    written = output.write_output(df, dest)
    assert written == dest
    assert dest.exists()
    assert pd.read_csv(dest).shape == (2, 3)


def test_write_output_provenance_sidecar(tmp_path, df):
    dest = tmp_path / "standardized.csv"
    prov = {"age_at_menarche": {"source_column_name": "RHQ010", "human_reviewed": False}}
    output.write_output(df, dest, provenance=prov)
    sidecar = tmp_path / "standardized_provenance.json"
    assert sidecar.exists()
    assert json.loads(sidecar.read_text())["age_at_menarche"]["source_column_name"] == "RHQ010"


def test_write_output_filelike_requires_fmt(df):
    with pytest.raises(output.UnsupportedFormatError):
        output.write_output(df, io.BytesIO())


def test_write_output_filelike_binary(df):
    buf = io.BytesIO()
    output.write_output(df, buf, fmt="parquet")
    assert buf.getvalue()[:4] == b"PAR1"
