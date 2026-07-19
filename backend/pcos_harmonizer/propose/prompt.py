"""Prompt templates for the propose step (the only LLM step).

These are curated working defaults so the app can be tested against a real LLM
today. Claudia may refine the wording; keep the **output JSON contracts** below
stable so the deterministic parsers in ``proposer.py`` / ``value_mapper.py`` keep

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

from ..config import SCHEMA_PATH
from . import _helpers

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


VALUE_MAPPING_SYSTEM = """You are a data-mapping assistant for a PCOS research
harmonization tool.

A column from a research dataset has already been matched to a field in the
canonical schema. Your job is now narrower: for each distinct value observed
in that column, choose which of the provided numbered options it corresponds
to.

You will receive:
- options: a numbered list of valid targets for this column. Each has an id
  and a label.
- values: the distinct values found in the column, each with how often it
  occurs, most frequent first.

Rules:
- Return exactly one entry per value given to you. Never omit a value and
  never invent one.
- Match each value to the id of the option whose label best describes it.
  Return the id only - never the label text.
- Options labeled "(missing/sentinel code, not a real answer)" represent
  refused, don't-know, not-applicable, or otherwise uninterpretable
  responses, rather than real categories. Datasets commonly encode these as
  out-of-range numbers such as 7, 9, 77, 99, 777, or 999.
- Use frequency as evidence. A value that is rare relative to the column's
  other values is more likely a sentinel than a genuine category, especially
  in a column with only two to four real categories. A value that is common
  is unlikely to be a sentinel.
- Judge only from the values and counts shown. Do not assume a coding
  convention from a dataset you were not shown.
- If a value cannot be confidently matched to any option, set target_id to
  null and give an unmapped_reason. A gap is reviewable; a wrong mapping is
  not, and silently corrupts every downstream analysis of this column.

Respond only with JSON conforming to the provided response schema. Do not
include commentary, explanations, or markdown formatting outside the JSON."""


def build_system_prompt(schema_path: str | None = None):
    """Return the system prompt for a column-mapping batch."""
    catalog = _helpers.build_field_catalog(schema_path or SCHEMA_PATH)
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
    return build_system_prompt(), user


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


# TODO: Use this user_prompt generator instead of the above, once the LLM is ready to handle it.
def build_value_mapping_call(field_id, allowed_values, observed_values):
    """Returns (system_prompt, user_message) for one enum column."""
    options = _helpers.build_value_options(allowed_values)
    user_message = json.dumps({
        "field_id": field_id,
        "options": options,
        "values": observed_values,
    })
    return VALUE_MAPPING_SYSTEM, user_message

