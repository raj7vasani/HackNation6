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
from .pipeline import PipelineResult, run_from_mapping, run_pipeline

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


def _run_demo(paths, notes: list[str]) -> PipelineResult | None:
    mp = curated_mapping_for(paths)
    if mp is None:
        notes.append("no curated demo mapping bundled for these files")
        return None
    return run_from_mapping(paths, mp, source=None)


def analyze(
    paths,
    engine: str = "llm",
    source: str | None = "nhanes",
) -> AnalysisOutcome:
    """Run the pipeline with graceful degradation.

    ``engine``: "llm" (LLM with fallback), "heuristic" (offline), or "demo"
    (curated mapping only).
    """
    paths = [Path(p) for p in paths]
    if not paths:
        raise ValueError("No input files provided.")
    engine = engine if engine in ENGINES else "llm"
    notes: list[str] = []

    if engine == "demo":
        result = _run_demo(paths, notes)
        if result is not None:
            return AnalysisOutcome(result, "demo", engine, notes)
        engine = "heuristic"  # fall through if no snapshot

    if engine == "llm":
        if get_openai_api_key():
            try:
                result = run_pipeline(paths, client="auto", source=source, write_mapping=False)
                return AnalysisOutcome(result, "llm", "llm", notes)
            except Exception as exc:  # network/quota/parse — degrade gracefully
                notes.append(f"LLM run failed ({exc}); falling back to heuristic")
        else:
            notes.append("no OPENAI_API_KEY; using heuristic mapping")

    # Heuristic (offline, deterministic)
    try:
        result = run_pipeline(paths, client=None, source=source, write_mapping=False)
        return AnalysisOutcome(result, "heuristic", engine, notes)
    except Exception as exc:
        notes.append(f"heuristic run failed ({exc}); trying curated demo")

    # Last resort: curated demo mapping
    result = _run_demo(paths, notes)
    if result is not None:
        return AnalysisOutcome(result, "demo", engine, notes)

    raise RuntimeError("Analysis failed on all engines: " + "; ".join(notes))
