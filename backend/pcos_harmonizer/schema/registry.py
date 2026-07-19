"""Field registry built from ``pcos_schema_v0.1.json``.

Turns the JSON Schema (with its ``x_*`` extensions) into typed :class:`Field`
objects and a :class:`FieldRegistry` with the lookups the rest of the pipeline
needs. This module does no I/O; see :mod:`.loader`.
"""

from __future__ import annotations

from dataclasses import dataclass, field as dc_field
from typing import Any

# JSON $defs ref name → simple type.
_REF_TYPE = {
    "nullable_number": "number",
    "nullable_integer": "integer",
    "nullable_boolean": "boolean",
    "nullable_string": "string",
}


@dataclass(frozen=True)
class Field:
    """A single canonical schema field."""

    name: str
    type: str  # number | integer | boolean | string | enum | array | date
    group: str | None = None
    unit: str | None = None
    enum: tuple[str, ...] | None = None
    x_range: tuple[float, float] | None = None
    hints: tuple[str, ...] = ()
    conversions: dict[str, Any] = dc_field(default_factory=dict)
    derivable: str | None = None
    priority: str | None = None
    note: str | None = None

    @property
    def is_numeric(self) -> bool:
        return self.type in ("number", "integer")

    @property
    def is_boolean(self) -> bool:
        return self.type == "boolean"

    @property
    def is_enum(self) -> bool:
        return self.type == "enum"

    @property
    def is_non_numeric(self) -> bool:
        """Fields that carry categorical values needing value standardization."""
        return self.type in ("enum", "boolean")

    @property
    def is_derived(self) -> bool:
        return self.derivable is not None

    @property
    def preserve_verbatim(self) -> bool:
        """Free-text fields the spec says to keep as-is (e.g. race_ethnicity)."""
        return bool(self.note) and "verbatim" in self.note.lower()


def _resolve_type(prop: dict[str, Any]) -> tuple[str, tuple[str, ...] | None]:
    """Return (type, enum_values) for a property schema."""
    if "$ref" in prop:
        ref = prop["$ref"].rsplit("/", 1)[-1]
        return _REF_TYPE.get(ref, "string"), None

    if "anyOf" in prop:
        for sub in prop["anyOf"]:
            if "enum" in sub:
                return "enum", tuple(sub["enum"])
        for sub in prop["anyOf"]:
            if sub.get("type") == "array":
                items = sub.get("items", {})
                return "array", tuple(items.get("enum", ())) or None
        for sub in prop["anyOf"]:
            if sub.get("format") == "date":
                return "date", None
        return "string", None

    t = prop.get("type")
    if isinstance(t, list):
        t = next((x for x in t if x != "null"), "string")
    return t or "string", None


def build_field(name: str, prop: dict[str, Any]) -> Field:
    ftype, enum = _resolve_type(prop)
    x_range = prop.get("x_range")
    return Field(
        name=name,
        type=ftype,
        group=prop.get("x_group"),
        unit=prop.get("x_unit"),
        enum=enum,
        x_range=tuple(x_range) if x_range else None,
        hints=tuple(prop.get("x_hints", ())),
        conversions=dict(prop.get("x_conversions", {})),
        derivable=prop.get("x_derivable"),
        priority=prop.get("x_priority"),
        note=prop.get("x_note"),
    )


class FieldRegistry:
    """Lookups over the canonical schema fields."""

    def __init__(self, schema: dict[str, Any]) -> None:
        self._schema = schema
        self._fields: dict[str, Field] = {}
        for name, prop in schema.get("properties", {}).items():
            if name.startswith("_"):  # skip _provenance
                continue
            self._fields[name] = build_field(name, prop)

    # -- basic access -------------------------------------------------------
    def __contains__(self, name: str) -> bool:
        return name in self._fields

    def __iter__(self):
        return iter(self._fields.values())

    def __len__(self) -> int:
        return len(self._fields)

    def get(self, name: str) -> Field | None:
        return self._fields.get(name)

    def all_fields(self) -> list[Field]:
        return list(self._fields.values())

    def names(self) -> list[str]:
        return list(self._fields)

    # -- grouped views ------------------------------------------------------
    def groups(self) -> list[str]:
        seen: list[str] = []
        for f in self._fields.values():
            if f.group and f.group not in seen:
                seen.append(f.group)
        return seen

    def fields_in_group(self, group: str) -> list[Field]:
        return [f for f in self._fields.values() if f.group == group]

    def derivable_fields(self) -> list[Field]:
        return [f for f in self._fields.values() if f.is_derived]

    def critical_fields(self) -> list[Field]:
        return [f for f in self._fields.values() if f.priority == "critical"]

    def non_numeric_fields(self) -> list[Field]:
        return [f for f in self._fields.values() if f.is_non_numeric]

    def conversions(self) -> dict[str, dict[str, Any]]:
        """field name → x_conversions (test oracle for the unit converter)."""
        return {f.name: dict(f.conversions) for f in self._fields.values() if f.conversions}

    # -- schema extras ------------------------------------------------------
    @property
    def raw_schema(self) -> dict[str, Any]:
        return self._schema

    @property
    def coverage_config(self) -> dict[str, Any]:
        return self._schema.get("x_coverage_report", {})

    @property
    def validator_rules(self) -> list[str]:
        return list(self._schema.get("x_validator_rules", []))
