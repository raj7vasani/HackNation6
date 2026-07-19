"""Write a standardized/canonical table to a user-selected file format.

The canonical deliverable is JSON conforming to ``pcos_schema_v0.1.json`` (values
plus a nested ``_provenance`` map). Other formats are flattened views of that
table: for flat tabular formats the canonical values are written and, when
provenance is supplied, it is emitted as a ``<name>_provenance.json`` sidecar.

Typical use::

    write_output(df, "standardized.xlsx")           # format inferred from suffix
    write_output(df, dest, fmt="parquet")           # explicit format
    payload = to_bytes(df, "csv")                    # bytes for a download button
"""

from __future__ import annotations

import io
import json
import tempfile
from pathlib import Path
from typing import IO, Any

import pandas as pd

__all__ = [
    "SUPPORTED_FORMATS",
    "UnsupportedFormatError",
    "normalize_format",
    "infer_format",
    "to_bytes",
    "write_output",
]


class UnsupportedFormatError(ValueError):
    """Raised when a requested output format is not supported."""


# Canonical format key -> metadata. ``binary`` controls text vs. bytes handling.
SUPPORTED_FORMATS: dict[str, dict[str, Any]] = {
    "csv": {"ext": ".csv", "binary": False},
    "tsv": {"ext": ".tsv", "binary": False},
    "json": {"ext": ".json", "binary": False},
    "jsonl": {"ext": ".jsonl", "binary": False},
    "xlsx": {"ext": ".xlsx", "binary": True},
    "parquet": {"ext": ".parquet", "binary": True},
    "stata": {"ext": ".dta", "binary": True},
    "xpt": {"ext": ".xpt", "binary": True},
}

# Friendly aliases the UI / user might pass.
_ALIASES = {
    "excel": "xlsx",
    "xls": "xlsx",
    "dta": "stata",
    "xport": "xpt",
    "sas": "xpt",
    "ndjson": "jsonl",
    "text": "csv",
    "txt": "csv",
}

# Map file extension -> canonical format key.
_EXT_TO_FORMAT = {meta["ext"]: fmt for fmt, meta in SUPPORTED_FORMATS.items()}
_EXT_TO_FORMAT[".dta"] = "stata"


def normalize_format(fmt: str) -> str:
    """Resolve a user-supplied format string to a canonical key."""
    if not fmt:
        raise UnsupportedFormatError("No output format given.")
    key = fmt.strip().lower().lstrip(".")
    key = _ALIASES.get(key, key)
    if key not in SUPPORTED_FORMATS:
        raise UnsupportedFormatError(
            f"Unsupported format {fmt!r}. Supported: {', '.join(sorted(SUPPORTED_FORMATS))}."
        )
    return key


def infer_format(path: str | Path) -> str:
    """Infer the canonical format key from a path's extension."""
    suffix = Path(path).suffix.lower()
    fmt = _EXT_TO_FORMAT.get(suffix)
    if fmt is None:
        raise UnsupportedFormatError(
            f"Cannot infer format from {Path(path).name!r}. "
            f"Use one of: {', '.join(sorted(e for e in _EXT_TO_FORMAT))}, or pass fmt=."
        )
    return fmt


def _require(module: str, fmt: str) -> None:
    """Give a clear error if an optional dependency for a format is missing."""
    import importlib.util

    if importlib.util.find_spec(module) is None:
        raise UnsupportedFormatError(
            f"Writing {fmt!r} needs the optional dependency {module!r}. "
            f"Install it with: pip install {module}"
        )


def _write_frame(df: pd.DataFrame, buf: IO[Any], fmt: str) -> None:
    """Write ``df`` to an open buffer in the given canonical format."""
    if fmt == "csv":
        df.to_csv(buf, index=False)
    elif fmt == "tsv":
        df.to_csv(buf, index=False, sep="\t")
    elif fmt == "json":
        buf.write(df.to_json(orient="records", indent=2, date_format="iso"))
    elif fmt == "jsonl":
        buf.write(df.to_json(orient="records", lines=True, date_format="iso"))
    elif fmt == "xlsx":
        _require("openpyxl", fmt)
        with pd.ExcelWriter(buf, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="standardized")
    elif fmt == "parquet":
        _require("pyarrow", fmt)
        df.to_parquet(buf, index=False)
    elif fmt == "stata":
        df.to_stata(buf, write_index=False, version=118)
    elif fmt == "xpt":
        _write_xport(df, buf)
    else:  # pragma: no cover - guarded by normalize_format
        raise UnsupportedFormatError(f"Unsupported format {fmt!r}.")


def _write_xport(df: pd.DataFrame, buf: IO[Any]) -> None:
    """Write SAS XPORT via pyreadstat (needs a real path; use a temp file).

    Uses XPORT v8 so canonical field names longer than 8 chars are preserved.
    """
    _require("pyreadstat", "xpt")
    import pyreadstat

    with tempfile.NamedTemporaryFile(suffix=".xpt", delete=True) as tmp:
        try:
            pyreadstat.write_xport(df, tmp.name, file_format_version=8)
        except TypeError:
            # Older pyreadstat without the version kwarg.
            pyreadstat.write_xport(df, tmp.name)
        tmp.seek(0)
        buf.write(Path(tmp.name).read_bytes())


def to_bytes(df: pd.DataFrame, fmt: str) -> bytes:
    """Serialize ``df`` to bytes in ``fmt`` (handy for download buttons)."""
    key = normalize_format(fmt)
    if SUPPORTED_FORMATS[key]["binary"]:
        buf = io.BytesIO()
        _write_frame(df, buf, key)
        return buf.getvalue()
    text_buf = io.StringIO()
    _write_frame(df, text_buf, key)
    return text_buf.getvalue().encode("utf-8")


def write_output(
    df: pd.DataFrame,
    destination: str | Path | IO[Any],
    fmt: str | None = None,
    *,
    provenance: dict[str, Any] | None = None,
) -> Path | None:
    """Write ``df`` to ``destination`` in ``fmt``.

    ``destination`` may be a filesystem path or an open file-like object. When it
    is a path, ``fmt`` defaults to the file extension. When ``provenance`` is given
    and the format cannot embed it (i.e. not JSON/JSONL), it is written next to the
    output as ``<name>_provenance.json``.

    Returns the written :class:`~pathlib.Path` for path destinations, else ``None``.
    """
    is_path = isinstance(destination, (str, Path))

    if fmt is not None:
        key = normalize_format(fmt)
    elif is_path:
        key = infer_format(destination)
    else:
        raise UnsupportedFormatError(
            "fmt is required when writing to a file-like object."
        )

    if is_path:
        path = Path(destination)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(to_bytes(df, key))
        if provenance is not None and key not in ("json", "jsonl"):
            sidecar = path.with_name(f"{path.stem}_provenance.json")
            sidecar.write_text(json.dumps(provenance, indent=2), encoding="utf-8")
        return path

    # File-like object: respect its binary/text nature.
    payload = to_bytes(df, key)
    try:
        destination.write(payload)
    except TypeError:
        destination.write(payload.decode("utf-8"))
    return None
