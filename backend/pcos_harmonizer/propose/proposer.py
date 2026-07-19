"""Column mapping proposer (pipeline step [3a]).

Uses the LLM when a client is supplied, otherwise a deterministic heuristic that
leans on the schema's ``x_hints`` (which include NHANES variable codes). Either
way the output is *proposals only*: ``human_reviewed`` stays False and nothing
here touches the numeric transform path.
"""

from __future__ import annotations

import re
from typing import Any

from ..mapping.model import MappingEntry
from ..profile.profiler import ColumnProfile
from ..schema.registry import Field, FieldRegistry
from . import prompt as prompt_mod
from .client import LLMClient

_WORD_RE = re.compile(r"[a-z0-9]+")


def _tokens(text: str | None) -> set[str]:
    return set(_WORD_RE.findall((text or "").lower()))


def _candidate_fields(registry: FieldRegistry) -> list[dict[str, Any]]:
    """Compact field descriptors for the LLM prompt (non-derived fields)."""
    out = []
    for f in registry.all_fields():
        if f.is_derived:
            continue
        out.append(
            {
                "name": f.name,
                "group": f.group,
                "type": f.type,
                "unit": f.unit,
                "enum": list(f.enum) if f.enum else None,
                "hints": list(f.hints),
            }
        )
    return out


# --------------------------------------------------------------------------
# Heuristic (offline) path
# --------------------------------------------------------------------------
def _build_hint_index(registry: FieldRegistry) -> dict[str, str]:
    index: dict[str, str] = {}
    for f in registry.all_fields():
        if f.is_derived:
            continue
        for hint in f.hints:
            index.setdefault(hint.lower(), f.name)
        index.setdefault(f.name.lower(), f.name)
    return index


def _heuristic_match(
    profile: ColumnProfile, registry: FieldRegistry, hint_index: dict[str, str]
) -> tuple[str | None, float, str]:
    col = profile.source_column.lower()
    # 1. Exact hint / code match (NHANES codes live in x_hints).
    if col in hint_index:
        return hint_index[col], 0.9, f"column code {profile.source_column!r} is a schema hint"

    label_tokens = _tokens(profile.label)
    col_tokens = _tokens(profile.source_column)
    all_tokens = label_tokens | col_tokens

    # 2. A multi-word hint fully contained in the label.
    best: tuple[str | None, float, str] = (None, 0.0, "no confident match")
    for f in registry.all_fields():
        if f.is_derived:
            continue
        for hint in f.hints:
            htok = _tokens(hint)
            if not htok:
                continue
            if htok <= all_tokens:
                score = 0.6 + 0.05 * len(htok)
                if score > best[1]:
                    best = (f.name, min(score, 0.85), f"hint {hint!r} matches label tokens")
        # 3. Field-name token overlap with the label.
        name_tok = _tokens(f.name)
        overlap = name_tok & label_tokens
        if overlap:
            score = 0.4 + 0.1 * len(overlap)
            if score > best[1]:
                best = (f.name, min(score, 0.7), f"field name tokens {sorted(overlap)} in label")
    return best


def _infer_unit_raw(profile: ColumnProfile, field: Field | None) -> str | None:
    for sig in profile.unit_signals:
        if sig.startswith("label_unit:"):
            return sig.split(":", 1)[1]
    return None


# --------------------------------------------------------------------------
# LLM path
# --------------------------------------------------------------------------
def _propose_llm(
    profiles: list[ColumnProfile], registry: FieldRegistry, client: LLMClient
) -> dict[str, dict[str, Any]]:
    if not profiles:
        return {}
    source_file = profiles[0].source_file
    columns = [p.to_llm_input() for p in profiles]
    system, user = prompt_mod.build_column_mapping_prompt(
        source_file, columns, _candidate_fields(registry)
    )
    data = client.complete_json(system, user)
    result: dict[str, dict[str, Any]] = {}
    for m in data.get("mappings", []):
        qid = m.get("question_id")
        if qid is not None:
            result[str(qid)] = m
    return result


# --------------------------------------------------------------------------
# Public entry point
# --------------------------------------------------------------------------
def propose_columns(
    profiles: list[ColumnProfile],
    registry: FieldRegistry,
    client: LLMClient | None = None,
    overrides: dict[str, dict[str, Any]] | None = None,
) -> list[MappingEntry]:
    """Propose a :class:`MappingEntry` per source column.

    ``overrides`` maps ``source_column`` → ``{"field": ..., "unit": ...}`` and
    takes precedence (authoritative source overrides, e.g. ``sources/nhanes.yaml``).
    """
    overrides = overrides or {}
    llm_by_col: dict[str, dict[str, Any]] = {}
    if client is not None:
        try:
            llm_by_col = _propose_llm(profiles, registry, client)
        except Exception:
            llm_by_col = {}  # fall back to heuristic per-column

    hint_index = _build_hint_index(registry)
    entries: list[MappingEntry] = []

    for p in profiles:
        ov = overrides.get(p.source_column)
        if ov and ov.get("field"):
            field = registry.get(ov["field"])
            entries.append(
                MappingEntry(
                    source_file=p.source_file,
                    source_column=p.source_column,
                    canonical_field=ov["field"],
                    unit_raw=ov.get("unit"),
                    unit_canonical=field.unit if field else None,
                    mapping_confidence=1.0,
                    mapping_rationale="source override",
                    source="override",
                )
            )
            continue

        llm = llm_by_col.get(p.source_column)
        if llm is not None:
            cf = llm.get("canonical_field")
            field = registry.get(cf) if cf else None
            entries.append(
                MappingEntry(
                    source_file=p.source_file,
                    source_column=p.source_column,
                    canonical_field=cf if field else None,
                    unit_raw=llm.get("unit_raw") or _infer_unit_raw(p, field),
                    unit_canonical=field.unit if field else None,
                    mapping_confidence=llm.get("mapping_confidence"),
                    mapping_rationale=llm.get("mapping_rationale"),
                    source="llm",
                )
            )
            continue

        cf, conf, rationale = _heuristic_match(p, registry, hint_index)
        field = registry.get(cf) if cf else None
        entries.append(
            MappingEntry(
                source_file=p.source_file,
                source_column=p.source_column,
                canonical_field=cf,
                unit_raw=_infer_unit_raw(p, field),
                unit_canonical=field.unit if field else None,
                mapping_confidence=round(conf, 2),
                mapping_rationale=rationale,
                source="heuristic",
            )
        )

    return entries
