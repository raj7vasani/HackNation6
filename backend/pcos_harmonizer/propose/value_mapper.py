"""Value standardization proposer (pipeline step [3b]).

For every mapped column whose canonical field is non-numeric (enum/bool), propose
a ``value_map: {raw_value → canonical_value}`` from the column's *unique* values
(once per column, not per row). LLM when a client is given, else a heuristic.
Unmapped raw values are left out → blocked for human review, never guessed.
"""

from __future__ import annotations

from typing import Any

from ..schema.registry import Field
from ..transform.missingness import normalize_value_key
from . import prompt as prompt_mod
from .client import LLMClient

_TRUE_TOKENS = {"1", "yes", "y", "true", "t", "present", "positive"}
_FALSE_TOKENS = {"0", "2", "no", "n", "false", "f", "absent", "negative"}

# Common categorical synonyms → canonical enum tokens.
_ENUM_SYNONYMS = {
    "current": {"current", "currently", "yes", "1", "active"},
    "former": {"former", "past", "previous", "ex"},
    "never": {"never", "no", "none", "0"},
    "male": {"male", "m", "1"},
    "female": {"female", "f", "2"},
    "yes": {"yes", "y", "1", "true"},
    "no": {"no", "n", "0", "2", "false"},
}


def _norm(v: Any) -> str:
    # Normalize "1.0" -> "1" first (XPT float codes), then lowercase.
    return normalize_value_key(v).strip().lower()


def _heuristic_value_map(field: Field, unique_values: list[Any]) -> dict[str, Any] | None:
    if field.is_boolean:
        out: dict[str, Any] = {}
        for v in unique_values:
            key = normalize_value_key(v)
            n = _norm(v)
            if n in _TRUE_TOKENS:
                out[key] = True
            elif n in _FALSE_TOKENS:
                out[key] = False
        return out or None

    if field.is_enum and field.enum:
        allowed = {e.lower(): e for e in field.enum}
        out = {}
        for v in unique_values:
            key = normalize_value_key(v)
            n = _norm(v)
            if n in allowed:  # exact match
                out[key] = allowed[n]
                continue
            for canon in field.enum:  # synonym match
                syn = _ENUM_SYNONYMS.get(canon.lower())
                if syn and n in syn:
                    out[key] = canon
                    break
        return out or None

    return None


def _llm_value_map(
    field: Field, unique_values: list[Any], client: LLMClient, context: str | None = None
) -> dict[str, Any] | None:
    allowed = list(field.enum) if field.enum else [True, False]
    payload = [{"raw": str(v)} for v in unique_values]
    system, user = prompt_mod.build_value_mapping_prompt(
        field.name, allowed, payload, column_description=context
    )
    data = client.complete_json(system, user)
    out: dict[str, Any] = {}
    for item in data.get("value_map", []):
        raw = item.get("raw")
        canon = item.get("canonical")
        if raw is not None and canon is not None:
            out[str(raw)] = canon
    return out or None


def propose_value_map(
    field: Field,
    unique_values: list[Any],
    client: LLMClient | None = None,
    context: str | None = None,
) -> dict[str, Any] | None:
    """Return a ``value_map`` for a non-numeric field, or None if not applicable.

    ``context`` is the source column's label/question text (e.g. contains a
    "1=yes, 2=no" legend); it is critical for correctly decoding numeric codes.
    None means: numeric field, verbatim-preserve field, or no confident mappings
    (the latter blocks the raw values for review).
    """
    if field.is_numeric or field.preserve_verbatim or not field.is_non_numeric:
        return None
    if client is not None:
        try:
            return _llm_value_map(field, unique_values, client, context=context)
        except Exception:
            pass
    return _heuristic_value_map(field, unique_values)
