"""PCOS Harmonizer backend package.

Turns raw research datasets (CSV / XPT / XLSX) into files conforming to the PCOS
canonical schema via an auditable pipeline:

    ingest → profile → propose (LLM) → review → transform → derive → validate → report

The LLM runs only in the *propose* step; everything from *transform* onward is
deterministic. See the module docstrings for details.
"""

from .app_api import AnalysisOutcome, analyze, default_inputs
from .chat import DataChatAssistant, build_data_context, chat_available
from .output import (
    SUPPORTED_FORMATS,
    UnsupportedFormatError,
    infer_format,
    normalize_format,
    to_bytes,
    write_output,
)
from .pipeline import PipelineResult, build_mapping, run_from_mapping, run_pipeline
from .schema.loader import get_registry, load_registry, load_schema

__all__ = [
    "SUPPORTED_FORMATS",
    "UnsupportedFormatError",
    "AnalysisOutcome",
    "DataChatAssistant",
    "PipelineResult",
    "analyze",
    "build_data_context",
    "build_mapping",
    "chat_available",
    "default_inputs",
    "get_registry",
    "infer_format",
    "load_registry",
    "load_schema",
    "normalize_format",
    "run_from_mapping",
    "run_pipeline",
    "to_bytes",
    "write_output",
]
