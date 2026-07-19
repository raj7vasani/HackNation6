"""Pydantic models for the reviewable mapping file (the pipeline contract)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field


class MappingEntry(BaseModel):
    """One source column → canonical field mapping."""

    source_file: str
    source_column: str
    canonical_field: str | None = None
    unit_raw: str | None = None
    unit_canonical: str | None = None
    transformation_applied: str | None = None
    mapping_confidence: float | None = None
    mapping_rationale: str | None = None
    source: Literal["override", "llm", "manual", "heuristic"] = "llm"
    human_reviewed: bool = False
    # Non-numeric fields only: {raw_value: canonical_value}. None = not applicable
    # or blocked (never guessed).
    value_map: dict[str, Any] | None = None


class UnmappedColumn(BaseModel):
    source_file: str
    source_column: str
    reason: str


class BlockedColumn(BaseModel):
    source_file: str
    source_column: str
    reason: str
    detail: str | None = None


class JoinSpec(BaseModel):
    key: str | None = None
    files: list[str] = Field(default_factory=list)


class MappingFile(BaseModel):
    """The full reviewable artifact emitted by propose and consumed by transform."""

    schema_version: str = "0.1.0"
    source_dataset: str | None = None
    generated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    generator: str = "pcos-harmonizer"
    join: JoinSpec = Field(default_factory=JoinSpec)
    mappings: list[MappingEntry] = Field(default_factory=list)
    unmapped_columns: list[UnmappedColumn] = Field(default_factory=list)
    blocked: list[BlockedColumn] = Field(default_factory=list)

    def active_mappings(self) -> list[MappingEntry]:
        """Entries that actually target a canonical field."""
        return [m for m in self.mappings if m.canonical_field]
