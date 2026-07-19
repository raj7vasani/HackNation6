"""Transform executor (pipeline step [5]).

Reads the reviewed mapping file and applies — deterministically and idempotently
— missingness decoding, the reviewed ``value_map``, and unit conversion. Emits a
per-field provenance record. No LLM here.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

import pandas as pd

from ..mapping.model import MappingEntry, MappingFile
from ..schema.registry import Field, FieldRegistry
from . import missingness as miss
from .units import CannotConvert, convert


@dataclass
class ProvenanceRecord:
    """Mapping-level provenance for one canonical field (spec §5, _provenance shape)."""

    source_file: str
    source_column_name: str
    unit_raw: str | None
    unit_canonical: str | None
    transformation_applied: str
    mapping_confidence: float | None
    mapping_rationale: str | None
    human_reviewed: bool
    value_map: dict[str, Any] | None = None
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TransformResult:
    table: pd.DataFrame  # one row per subject; canonical fields
    provenance: dict[str, dict[str, Any]]
    warnings: list[str] = field(default_factory=list)


def _sentinel_map_for(sources: dict[str, Any] | None, column: str) -> dict[Any, str] | None:
    if not sources:
        return None
    sentinels = sources.get("sentinels", {})
    return sentinels.get(column)


def _apply_value(
    value: Any,
    sentinel_map: dict[Any, str] | None,
    value_map: dict[str, Any] | None,
    field_obj: Field,
    unit_raw: str | None,
) -> tuple[Any, str | None]:
    """Return (canonical_value, per_value_note) for a single raw value."""
    decoded = miss.decode_sentinel(value, sentinel_map)
    decoded = miss.code_missing(decoded)
    if miss.is_missing_code(decoded):
        return decoded, None

    # Non-numeric: apply reviewed value_map.
    if field_obj.is_non_numeric:
        if field_obj.preserve_verbatim:
            return decoded, None
        if value_map:
            nmap = {miss.normalize_value_key(k): v for k, v in value_map.items()}
            key = miss.normalize_value_key(decoded)
            if key in nmap:
                return nmap[key], None
            return miss.UNKNOWN, f"raw {decoded!r} not in value_map (blocked)"
        return decoded, None

    # Numeric: convert units when we know both sides and they differ.
    if field_obj.is_numeric:
        try:
            num = float(decoded)
        except (TypeError, ValueError):
            return miss.UNKNOWN, f"non-numeric raw {decoded!r} for numeric field"
        if unit_raw and field_obj.unit and unit_raw != field_obj.unit:
            try:
                out, _desc = convert(num, unit_raw, field_obj.unit, field_obj.name)
                return out, None
            except CannotConvert as exc:
                return miss.UNKNOWN, f"unit blocked: {exc}"
        return num, None

    return decoded, None


def _describe(entry: MappingEntry, field_obj: Field) -> str:
    if field_obj.is_numeric and entry.unit_raw and field_obj.unit and entry.unit_raw != field_obj.unit:
        try:
            _v, desc = convert(1.0, entry.unit_raw, field_obj.unit, field_obj.name)
            return desc
        except CannotConvert:
            return f"unit conversion blocked ({entry.unit_raw} -> {field_obj.unit})"
    if field_obj.is_non_numeric and entry.value_map:
        return "value_map applied"
    return "identity"


def transform(
    df: pd.DataFrame,
    mapping: MappingFile,
    registry: FieldRegistry,
    subject_key: str | None = None,
    sources: dict[str, Any] | None = None,
) -> TransformResult:
    """Apply the mapping to a (joined) DataFrame → canonical table + provenance."""
    subject_key = subject_key or mapping.join.key
    n = len(df)
    if subject_key and subject_key in df.columns:
        subject_ids = df[subject_key].tolist()
    else:
        subject_ids = list(range(n))

    out: dict[str, list[Any]] = {}
    provenance: dict[str, dict[str, Any]] = {}
    warnings: list[str] = []

    for entry in mapping.active_mappings():
        field_obj = registry.get(entry.canonical_field)  # type: ignore[arg-type]
        if field_obj is None:
            warnings.append(f"unknown canonical_field {entry.canonical_field!r}; skipped")
            continue
        if entry.source_column not in df.columns:
            warnings.append(f"column {entry.source_column!r} missing in data; skipped")
            continue

        sentinel_map = _sentinel_map_for(sources, entry.source_column)
        series = df[entry.source_column]
        col_values: list[Any] = []
        notes: set[str] = set()
        for raw in series:
            val, note = _apply_value(raw, sentinel_map, entry.value_map, field_obj, entry.unit_raw)
            col_values.append(val)
            if note:
                notes.add(note)

        fname = entry.canonical_field  # type: ignore[assignment]
        if fname in out:
            # Coalesce: fill only where the existing column is a missing code.
            existing = out[fname]
            out[fname] = [
                nv if miss.is_missing_code(ev) else ev for ev, nv in zip(existing, col_values)
            ]
            if fname in provenance:
                provenance[fname]["notes"].append(f"also from {entry.source_column}")
        else:
            out[fname] = col_values
            provenance[fname] = ProvenanceRecord(
                source_file=entry.source_file,
                source_column_name=entry.source_column,
                unit_raw=entry.unit_raw,
                unit_canonical=field_obj.unit,
                transformation_applied=_describe(entry, field_obj),
                mapping_confidence=entry.mapping_confidence,
                mapping_rationale=entry.mapping_rationale,
                human_reviewed=entry.human_reviewed,
                value_map=entry.value_map,
                notes=sorted(notes),
            ).to_dict()

    # subject_id column: use a mapped canonical subject_id if present, else the join key.
    subj_col = out.pop("subject_id", None) or [str(s) for s in subject_ids]
    table = pd.DataFrame({"subject_id": subj_col, **out})
    return TransformResult(table=table, provenance=provenance, warnings=warnings)
