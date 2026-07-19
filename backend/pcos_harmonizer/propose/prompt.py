"""Prompt templates for the propose step (the only LLM step).

These are curated working defaults so the app can be tested against a real LLM
today. Claudia may refine the wording; keep the **output JSON contracts** below
stable so the deterministic parsers in ``proposer.py`` / ``value_mapper.py`` keep
working.

Contracts:
  Column mapping → {"mappings": [{"question_id": str,
                                  "canonical_field": str | null,
                                  "unit_raw": str | null,
                                  "mapping_confidence": number,
                                  "mapping_rationale": str}]}
  Value mapping  → {"value_map": [{"raw": str, "canonical": <allowed> | null,
                                   "confidence": number}],
                    "unmapped": [str, ...],
                    "rationale": str}
"""

from __future__ import annotations

import json
from typing import Any

from . import _field_catalog

COLUMN_MAPPING_SYSTEM = """You are a data-mapping assistant for a PCOS research harmonization tool.
You will be given a list of source columns from one or more datasets, and a
catalog of canonical schema fields. Your job is to propose, for each source
column, which canonical field (if any) it corresponds to.

Rules:
- Return one entry per source column. Never omit a column; unmappable columns
  get field_id: null with an unmapped_reason.
- Prefer field_id: null over a low-confidence guess. A gap is visible and
  reviewable later; a wrong mapping is not, and can silently corrupt an
  analysis.
- Every field in the catalog is mappable, including fields that could also be
  computed from other fields (e.g. bmi, homa_ir). If a source column holds
  one of these directly, map it — the source value takes precedence over any
  fallback computation performed later.
- Infer the source unit from the column's value range, using the "range" and
  "note" fields in the catalog as a guide. Report the unit; do not convert
  the value yourself.
- If you cannot determine the unit with reasonable confidence, set
  unit_raw: null and add the flag UNIT_UNKNOWN. Do not guess.
- Map columns to fields only. Do not translate individual data values to
  enum values, and do not classify missingness/sentinel codes (e.g. 777,
  999) — both of those happen in a separate pass, not this one.
- Base every judgment on the column's name, label (if given), and sample
  values. Do not assume anything about the source dataset beyond what is
  shown to you.

Respond only with JSON conforming to the provided response schema. Do not
include commentary, explanations, or markdown formatting outside the JSON."""


VALUE_MAPPING_SYSTEM = """\
You standardize the categorical values of ONE column to the allowed values of a
canonical PCOS schema field.

You will receive:
- canonical_field: the target field name.
- column_description: the source column's label/question text. It OFTEN contains a
  code legend such as "(1=yes, 2=no)" or "(1=current, 2=former, 3=never)". When
  present, this legend is authoritative — use it to decide the direction.
- allowed_values: the exact set of values you may output (enum members, or the
  booleans true/false).
- unique_values: the distinct raw values found in the column (you are given the
  unique set, not every row).

Rules:
1. If column_description contains a code legend, follow it exactly. Do NOT guess
   the direction of a numeric code without the legend.
2. Map each raw value to exactly one allowed value, or null if you are not sure.
   PREFER null OVER A GUESS — unmapped values are flagged for human review, never
   silently dropped or coerced.
3. Absent a legend, common encodings are 1/yes/y/true → the "true"/"current"/
   "present" sense; 2/0/no/n/false → the "false"/"never"/"absent" sense.
4. Never invent a value outside allowed_values.
5. confidence is 0.0–1.0.

Return ONLY a JSON object of the form:
{"value_map":[{"raw":"...","canonical":<allowed>|null,"confidence":0.0}],
"unmapped":["..."],"rationale":"..."}
Every input raw value must appear exactly once across "value_map" (as a mapping)
and/or be listed in "unmapped".
"""


def build_system_prompt(schema_path="pcos_schema_v0.1.json"):
    catalog = _field_catalog.build_catalog(schema_path)
    return (
        COLUMN_MAPPING_SYSTEM
        + "\n\nCanonical field catalog:\n"
        + json.dumps(catalog, separators=(",", ":"))
    )


def build_column_mapping_prompt(
    source_file: str,
    columns: list[dict[str, Any]],
    candidate_fields: list[dict[str, Any]],
) -> tuple[str, str]:
    """Return (system, user) for a column-mapping batch."""
    user = json.dumps(
        {
            "source_file": source_file,
            "candidate_fields": candidate_fields,
            "columns": columns,
        },
        ensure_ascii=False,
        indent=2,
    )
    return COLUMN_MAPPING_SYSTEM, user


def build_value_mapping_prompt(
    canonical_field: str,
    allowed_values: list[Any],
    unique_values: list[dict[str, Any]],
    column_description: str | None = None,
) -> tuple[str, str]:
    """Return (system, user) for a single column's value standardization."""
    user = json.dumps(
        {
            "canonical_field": canonical_field,
            "column_description": column_description or "",
            "allowed_values": allowed_values,
            "unique_values": unique_values,
        },
        ensure_ascii=False,
        indent=2,
    )
    return VALUE_MAPPING_SYSTEM, user
