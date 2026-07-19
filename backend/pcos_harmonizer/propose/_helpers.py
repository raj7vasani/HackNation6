"""Generate the LLM field catalog from pcos_schema_v0.1.json.

Read fresh at runtime — never checked in — so the catalog can't drift from
the schema. Every field is included; there is no unmappable set.
"""
import json
from pathlib import Path

from ..config import SCHEMA_PATH


def enum_values(field_spec):
    """Pull enum values out of a nullable anyOf wrapper, if present."""
    if "enum" in field_spec:
        return field_spec["enum"]
    for branch in field_spec.get("anyOf", []):
        if "enum" in branch:
            return branch["enum"]
    return None


def field_type(field_spec):
    ref = field_spec.get("$ref", "")
    if "nullable_number" in ref:
        return "number"
    if "nullable_integer" in ref:
        return "integer"
    if "nullable_boolean" in ref:
        return "boolean"
    if "nullable_string" in ref:
        return "string"
    if enum_values(field_spec):
        return "enum"
    for branch in field_spec.get("anyOf", []):
        if branch.get("format") == "date":
            return "date"
    return "string"


def build_field_catalog(schema_path: str | Path | None = None):
    path = Path(schema_path) if schema_path else SCHEMA_PATH
    with open(path, encoding="utf-8") as fh:
        schema = json.load(fh)
    props = schema["properties"]

    fields = []
    for name, spec in props.items():
        if name.startswith("_"):
            continue
        if "x_id" not in spec:
            raise ValueError(f"{name} has no frozen x_id — assign one before use")

        entry = {"id": spec["x_id"], "field": name, "type": field_type(spec)}

        if spec.get("x_unit"):        entry["unit"] = spec["x_unit"]
        if spec.get("x_group"):       entry["group"] = spec["x_group"]
        if spec.get("x_range"):       entry["range"] = spec["x_range"]
        if spec.get("x_conversions"): entry["accepted_units"] = list(spec["x_conversions"].keys())
        if spec.get("x_hints"):       entry["hints"] = spec["x_hints"]
        if spec.get("x_note"):        entry["note"] = spec["x_note"]

        values = enum_values(spec)
        if values:
            entry["values"] = values

        fields.append(entry)

    ids = [f["id"] for f in fields]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate x_id in schema")

    return {
        "schema_version": schema.get("version", "0.1.0"),
        "field_count": len(fields),
        "missing_codes": [
            "not_measured", "below_lod", "not_applicable", "withheld", "unknown"
        ],
        "fields": fields,
    }


MISSING_CODES = ["not_measured", "below_lod", "not_applicable", "withheld", "unknown"]

def build_value_options(field_enum_values):
    """field_enum_values: the target field's own allowed values, e.g.
    ["current", "former", "never", "unknown"] for hormonal_contraceptive_use."""
    options = [
        {"id": i + 1, "label": v}
        for i, v in enumerate(field_enum_values)
    ]
    base = len(field_enum_values)
    options += [
        {"id": base + i + 1, "label": f"{v} (missing/sentinel code, not a real answer)"}
        for i, v in enumerate(MISSING_CODES)
    ]
    return options