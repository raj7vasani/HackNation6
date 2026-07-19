"""High-level entry point for the UI (and any other caller).

Wraps the pipeline with a robust fallback chain so a live demo always shows a
result:

    LLM (if requested + key present)  →  heuristic (offline)  →  curated demo mapping

The curated demo mapping (``mock_data/demo_snapshot/*.mapping.yaml``) is a
human-reviewed mapping that runs deterministically with no network, guaranteeing a
correct, presentable result even if the LLM and heuristic both fail.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .config import MOCK_DATA_DIR, get_openai_api_key, mock_data_files, use_mock_data
from .mapping.model import MappingFile
from .pipeline import (
    PipelineResult,
    ProgressCallback,
    propose_mapping,
    resume_pipeline,
    run_from_mapping,
    run_pipeline,
)

DEMO_SNAPSHOT_DIR = MOCK_DATA_DIR / "demo_snapshot"

# Input file name → curated (human-reviewed) mapping file.
CURATED_MAPPINGS: dict[str, Path] = {
    "mock_pcos_clinic.xpt": DEMO_SNAPSHOT_DIR / "mock_pcos_clinic.mapping.yaml",
}

ENGINES = ("llm", "heuristic", "demo")


@dataclass
class AnalysisOutcome:
    result: PipelineResult
    engine_used: str  # "llm" | "heuristic" | "demo"
    requested_engine: str
    notes: list[str] = field(default_factory=list)


def default_inputs() -> list[Path]:
    """Mock inputs when USE_MOCK_DATA is set, else empty."""
    return mock_data_files() if use_mock_data() else []


def curated_mapping_for(paths) -> Path | None:
    """Return a curated mapping if one of the inputs has one bundled."""
    names = {Path(p).name for p in paths}
    for name, mp in CURATED_MAPPINGS.items():
        if name in names and mp.exists():
            return mp
    return None


def _run_demo(
    paths,
    notes: list[str],
    on_progress: ProgressCallback | None = None,
) -> PipelineResult | None:
    mp = curated_mapping_for(paths)
    if mp is None:
        notes.append("no curated demo mapping bundled for these files")
        return None
    return run_from_mapping(paths, mp, source=None, on_progress=on_progress)


def analyze(
    paths,
    engine: str = "llm",
    source: str | None = "nhanes",
    on_progress: ProgressCallback | None = None,
) -> AnalysisOutcome:
    """Run the pipeline with graceful degradation.

    ``engine``: "llm" (LLM with fallback), "heuristic" (offline), or "demo"
    (curated mapping only).
    ``on_progress``: optional ``(step, total, message)`` callback for UI progress.
    """
    paths = [Path(p) for p in paths]
    if not paths:
        raise ValueError("No input files provided.")
    engine = engine if engine in ENGINES else "llm"
    notes: list[str] = []

    if engine == "demo":
        result = _run_demo(paths, notes, on_progress=on_progress)
        if result is not None:
            return AnalysisOutcome(result, "demo", engine, notes)
        engine = "heuristic"  # fall through if no snapshot

    if engine == "llm":
        if get_openai_api_key():
            try:
                result = run_pipeline(
                    paths,
                    client="auto",
                    source=source,
                    write_mapping=False,
                    on_progress=on_progress,
                )
                return AnalysisOutcome(result, "llm", "llm", notes)
            except Exception as exc:  # network/quota/parse — degrade gracefully
                notes.append(f"LLM run failed ({exc}); falling back to heuristic")
        else:
            notes.append("no OPENAI_API_KEY; using heuristic mapping")

    # Heuristic (offline, deterministic)
    try:
        result = run_pipeline(
            paths,
            client=None,
            source=source,
            write_mapping=False,
            on_progress=on_progress,
        )
        return AnalysisOutcome(result, "heuristic", engine, notes)
    except Exception as exc:
        notes.append(f"heuristic run failed ({exc}); trying curated demo")

    # Last resort: curated demo mapping
    result = _run_demo(paths, notes, on_progress=on_progress)
    if result is not None:
        return AnalysisOutcome(result, "demo", engine, notes)

    raise RuntimeError("Analysis failed on all engines: " + "; ".join(notes))


# ---------------------------------------------------------------------------
# Interactive (pause-for-review) flow
# ---------------------------------------------------------------------------
@dataclass
class ProposalOutcome:
    """Result of the propose phase — a reviewable mapping plus how it was made."""

    mapping: MappingFile
    engine_used: str  # "llm" | "heuristic"
    notes: list[str] = field(default_factory=list)


def propose_for_review(
    paths,
    engine: str = "llm",
    source: str | None = "nhanes",
    on_progress: ProgressCallback | None = None,
) -> ProposalOutcome:
    """Run steps [1]–[3] with graceful degradation, then STOP for human review.

    Same LLM→heuristic fallback as :func:`analyze`, but returns the mapping (with
    its ``blocked`` list) instead of finishing the run, so a caller can collect
    input on the stuck columns before calling :func:`complete_after_review`.
    """
    paths = [Path(p) for p in paths]
    if not paths:
        raise ValueError("No input files provided.")
    engine = engine if engine in ("llm", "heuristic") else "llm"
    notes: list[str] = []

    if engine == "llm":
        if get_openai_api_key():
            try:
                mapping = propose_mapping(paths, client="auto", source=source, on_progress=on_progress)
                return ProposalOutcome(mapping, "llm", notes)
            except Exception as exc:  # network/quota/parse — degrade gracefully
                notes.append(f"LLM propose failed ({exc}); falling back to heuristic")
        else:
            notes.append("no OPENAI_API_KEY; using heuristic mapping")

    mapping = propose_mapping(paths, client=None, source=source, on_progress=on_progress)
    return ProposalOutcome(mapping, "heuristic", notes)


def complete_after_review(
    paths,
    mapping: MappingFile,
    engine_used: str = "llm",
    source: str | None = "nhanes",
    notes: list[str] | None = None,
    on_progress: ProgressCallback | None = None,
) -> AnalysisOutcome:
    """Run the deterministic tail (steps [5]–[8]) on a reviewed mapping."""
    paths = [Path(p) for p in paths]
    if not paths:
        raise ValueError("No input files provided.")
    result = resume_pipeline(paths, mapping, source=source, on_progress=on_progress)
    return AnalysisOutcome(result, engine_used, engine_used, list(notes or []))
