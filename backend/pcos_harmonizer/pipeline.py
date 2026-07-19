"""End-to-end orchestration of steps [1]–[8].

Two entry points:
- :func:`run_pipeline` — ingest → profile → propose → transform → derive →
  validate → report (generates a reviewable mapping file).
- :func:`run_from_mapping` — deterministic re-run from an existing mapping file
  (steps [5]–[8] only); byte-identical output for the same mapping.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from . import config as cfg
from .derive import derive_all
from .ingest.multifile import join_files
from .ingest.readers import IngestedFile, read_files
from .mapping.io import write_mapping_file
from .mapping.model import BlockedColumn, JoinSpec, MappingEntry, MappingFile, UnmappedColumn
from .profile.profiler import profile_file
from .propose.client import LLMClient, get_default_client
from .propose.proposer import propose_columns
from .propose.value_mapper import propose_value_map
from .report.coverage import coverage_report, format_report
from .schema.loader import get_registry
from .schema.registry import FieldRegistry
from .transform.executor import transform
from .validate.validator import validate


@dataclass
class PipelineResult:
    table: pd.DataFrame
    provenance: dict[str, Any]
    mapping: MappingFile
    coverage: dict[str, Any]
    warnings: list[dict[str, Any]] = field(default_factory=list)
    mapping_path: Path | None = None
    output_path: Path | None = None

    @property
    def coverage_text(self) -> str:
        return format_report(self.coverage)


@lru_cache(maxsize=None)
def load_source_config(name: str | None) -> dict[str, Any]:
    """Load ``sources/<name>.yaml`` (overrides + sentinels), or empty if none."""
    if not name:
        return {}
    path = cfg.SOURCES_DIR / f"{name}.yaml"
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def _resolve_client(client: Any) -> LLMClient | None:
    if client == "auto":
        return get_default_client()
    return client  # None (heuristic) or an explicit LLMClient


def _unique_values(series: pd.Series, limit: int = 100) -> list[Any]:
    vals = series.dropna().unique().tolist()
    return vals[:limit]


def build_mapping(
    files: list[IngestedFile],
    registry: FieldRegistry,
    client: LLMClient | None,
    source: str | None,
) -> MappingFile:
    """Propose column mappings + value maps → a reviewable MappingFile."""
    source_cfg = load_source_config(source)
    overrides = source_cfg.get("overrides", {})

    join = join_files(files, key=source_cfg.get("join_key"))
    entries: list[MappingEntry] = []
    unmapped: list[UnmappedColumn] = []
    blocked: list[BlockedColumn] = []

    for f in files:
        profiles = profile_file(f)
        proposed = propose_columns(profiles, registry, client=client, overrides=overrides)
        prof_by_col = {p.source_column: p for p in profiles}
        for entry in proposed:
            if entry.canonical_field is None:
                unmapped.append(UnmappedColumn(
                    source_file=entry.source_file,
                    source_column=entry.source_column,
                    reason=entry.mapping_rationale or "no confident match",
                ))
                continue
            fld = registry.get(entry.canonical_field)
            if fld is None:
                continue
            # value standardization for non-numeric fields
            if fld.is_non_numeric and not fld.preserve_verbatim:
                uniques = _unique_values(f.df[entry.source_column]) if entry.source_column in f.df else []
                prof = prof_by_col.get(entry.source_column)
                context = prof.label if prof else None
                vmap = propose_value_map(fld, uniques, client=client, context=context)
                entry.value_map = vmap
            # block numeric fields whose unit could not be inferred
            if fld.is_numeric and fld.unit and not entry.unit_raw:
                blocked.append(BlockedColumn(
                    source_file=entry.source_file,
                    source_column=entry.source_column,
                    reason="unit_raw_unknown",
                    detail=f"canonical unit {fld.unit}; supply unit_raw before conversion",
                ))
            entries.append(entry)

    return MappingFile(
        source_dataset=source or (files[0].name if files else None),
        join=JoinSpec(key=join.key, files=join.files),
        mappings=entries,
        unmapped_columns=unmapped,
        blocked=blocked,
    )


def run_pipeline(
    input_paths,
    output_path: str | Path | None = None,
    output_format: str | None = None,
    client: Any = "auto",
    source: str | None = "nhanes",
    mapping_out: str | Path | None = None,
    write_mapping: bool = True,
) -> PipelineResult:
    """Full pipeline from raw files to canonical table + coverage report."""
    registry = get_registry()
    llm = _resolve_client(client)
    files = read_files(list(input_paths))

    mapping = build_mapping(files, registry, llm, source)

    if write_mapping:
        mapping_out = Path(mapping_out) if mapping_out else cfg.OUTPUT_DIR / "mapping.yaml"
        write_mapping_file(mapping, mapping_out)
    else:
        mapping_out = None

    source_cfg = load_source_config(source)
    join = join_files(files, key=mapping.join.key)

    result = _transform_and_report(join.df, mapping, registry, source_cfg, output_path, output_format)
    result.mapping = mapping
    result.mapping_path = Path(mapping_out) if mapping_out else None
    return result


def run_from_mapping(
    input_paths,
    mapping_path: str | Path,
    output_path: str | Path | None = None,
    output_format: str | None = None,
    source: str | None = "nhanes",
) -> PipelineResult:
    """Deterministic re-run from a reviewed mapping file (steps [5]–[8])."""
    from .mapping.io import read_mapping_file

    registry = get_registry()
    files = read_files(list(input_paths))
    mapping = read_mapping_file(mapping_path)
    source_cfg = load_source_config(source)
    join = join_files(files, key=mapping.join.key)
    result = _transform_and_report(join.df, mapping, registry, source_cfg, output_path, output_format)
    result.mapping = mapping
    result.mapping_path = Path(mapping_path)
    return result


def _transform_and_report(
    df: pd.DataFrame,
    mapping: MappingFile,
    registry: FieldRegistry,
    source_cfg: dict[str, Any],
    output_path: str | Path | None,
    output_format: str | None,
) -> PipelineResult:
    tr = transform(df, mapping, registry, subject_key=mapping.join.key, sources=source_cfg)
    table = tr.table
    warnings: list[Any] = list(tr.warnings)

    insulin_field = registry.get("fasting_insulin")
    derive_warnings = derive_all(table, insulin_unit=insulin_field.unit if insulin_field else None)
    warnings += derive_warnings

    validation = validate(table, registry)
    coverage = coverage_report(table, registry, tr.provenance)

    out_path = None
    if output_path is not None:
        from .output import write_output

        out_path = write_output(table, output_path, fmt=output_format, provenance=tr.provenance)

    combined = [{"rule": "transform_or_derive", "message": w, "severity": "warning"} for w in warnings]
    combined += validation

    return PipelineResult(
        table=table,
        provenance=tr.provenance,
        mapping=mapping,
        coverage=coverage,
        warnings=combined,
        output_path=Path(out_path) if out_path else None,
    )
