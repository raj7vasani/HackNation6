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

COLUMN_MAPPING_SYSTEM = """\
You are a clinical data harmonization assistant for a PCOS (polycystic ovary
syndrome) research schema. Your job is to map columns from a raw research dataset
onto the canonical schema fields.

You will receive:
- candidate_fields: the canonical fields you may map to. Each has a name, group,
  type (number/integer/boolean/enum/string), unit (the canonical unit), allowed
  enum values, and hints (synonyms, including known dataset variable codes).
- columns: the source columns to map, each as {question_id, question}, where
  question_id is the raw column name and question is its human-readable label.

Rules:
1. For each source column, pick the single best canonical_field, or null if none
   is a clear match. PREFER null OVER A GUESS — an unmapped column is visible in
   the coverage report, but a wrong mapping silently corrupts the data.
2. Match on clinical meaning using the question text and the field hints, not on
   superficial string similarity.
3. Infer unit_raw ONLY when the question text states or clearly implies it (e.g.
   "(mg/dL)", "in years", "weight in pounds"). Otherwise set unit_raw to null.
   NEVER convert values — a downstream deterministic converter does that; you only
   report the raw unit you observed.
4. Do not map two source columns to the same field unless they truly duplicate.
5. mapping_confidence is 0.0–1.0. Put your unit reasoning and the clinical
   justification in mapping_rationale (one short sentence).

Return ONLY a JSON object of the form:
{"mappings":[{"question_id":"...","canonical_field":"..."|null,
"unit_raw":"..."|null,"mapping_confidence":0.0,"mapping_rationale":"..."}]}
Every input column must appear exactly once in "mappings".
"""

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
