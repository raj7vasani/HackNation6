"""Human-in-the-loop review helpers (pipeline step [4]).

The proposer deliberately refuses to guess in two situations, both surfaced on the
:class:`~pcos_harmonizer.mapping.model.MappingFile`:

- ``blocked``   — a column mapped to a numeric field whose *unit* could not be
  inferred. It is the literal "stuck" case: the deterministic transform cannot
  convert without a unit. This is where interactive input is most valuable.
- ``unmapped``  — a column with no confident canonical field at all.

These helpers fold a reviewer's answers back into the mapping so it can be handed
to :func:`~pcos_harmonizer.pipeline.resume_pipeline`. They only *add* human
decisions; they never invent one.
"""

from __future__ import annotations

from .mapping.model import BlockedColumn, MappingEntry, MappingFile

# Plausible raw units to offer per canonical unit (first entry = the canonical
# unit itself, i.e. "already in canonical units, no conversion"). Kept small and
# clinically relevant; the converter accepts more than these.
UNIT_SUGGESTIONS: dict[str, list[str]] = {
    "nmol/L": ["nmol/L", "ng/dL", "ng/mL", "pg/mL"],
    "pmol/L": ["pmol/L", "pg/mL", "ng/dL", "uIU/mL", "mIU/L"],
    "mmol/L": ["mmol/L", "mg/dL"],
    "umol/L": ["umol/L", "mg/dL", "ug/dL"],
    "kg": ["kg", "lb"],
    "cm": ["cm", "in", "mm"],
    "mIU/L": ["mIU/L", "ng/mL", "IU/L"],
    "IU/L": ["IU/L", "mIU/mL"],
    "mL": ["mL", "cm^3"],
    "%": ["%", "mmol/mol (IFCC)"],
}


def pending_units(mapping: MappingFile) -> list[BlockedColumn]:
    """Columns blocked on an unknown unit — the interactive review queue."""
    return list(mapping.blocked)


def entry_for(mapping: MappingFile, source_column: str) -> MappingEntry | None:
    for e in mapping.mappings:
        if e.source_column == source_column:
            return e
    return None


def unit_options(canonical_unit: str | None) -> list[str]:
    """Suggested raw-unit choices for a blocked column, canonical unit first."""
    if not canonical_unit:
        return []
    opts = UNIT_SUGGESTIONS.get(canonical_unit)
    if opts:
        return list(opts)
    return [canonical_unit]


def apply_unit_answers(mapping: MappingFile, answers: dict[str, str]) -> MappingFile:
    """Set ``unit_raw`` for the answered columns, mark them reviewed, and drop them
    from ``blocked``.

    ``answers`` maps ``source_column`` → chosen raw unit. Empty/absent answers are
    left unresolved (the column stays blocked and its value passes through
    unconverted, exactly as before). Mutates and returns the same mapping.
    """
    resolved: set[str] = set()
    for entry in mapping.mappings:
        chosen = (answers.get(entry.source_column) or "").strip()
        if not chosen:
            continue
        entry.unit_raw = chosen
        entry.human_reviewed = True
        if entry.mapping_rationale:
            entry.mapping_rationale += " | unit confirmed by reviewer"
        else:
            entry.mapping_rationale = "unit confirmed by reviewer"
        resolved.add(entry.source_column)

    if resolved:
        mapping.blocked = [b for b in mapping.blocked if b.source_column not in resolved]
    return mapping
