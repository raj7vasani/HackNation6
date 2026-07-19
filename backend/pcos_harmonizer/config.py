"""Paths, model settings, and .env loading for the harmonizer."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path


def find_repo_root(start: Path | str | None = None) -> Path:
    """Walk upward until the canonical schema JSON is found."""
    p = Path(start or __file__).resolve()
    for parent in [p, *p.parents]:
        if (
            (parent / "backend" / "pcos_harmonizer" / "resources" / "pcos_schema_v0.1.json").exists()
            or (parent / "docs" / "pcos_schema_v0.1.json").exists()
        ):
            return parent
    # Fallback: backend/pcos_harmonizer/config.py → repo root is two levels up.
    return Path(__file__).resolve().parents[2]


REPO_ROOT = find_repo_root()
SCHEMA_PATH = REPO_ROOT / "backend" / "pcos_harmonizer" / "resources" / "pcos_schema_v0.1.json"
if not SCHEMA_PATH.exists():
    SCHEMA_PATH = REPO_ROOT / "docs" / "pcos_schema_v0.1.json"
DATA_DIR = REPO_ROOT / "data"
MOCK_DATA_DIR = REPO_ROOT / "mock_data"
OUTPUT_DIR = REPO_ROOT / "outputs"
SOURCES_DIR = Path(__file__).resolve().parent / "sources"

_INPUT_SUFFIXES = (".xpt", ".csv", ".tsv", ".xlsx", ".xls")

# Confidence below this blocks a mapping for human review rather than applying it.
CONFIDENCE_THRESHOLD = float(os.environ.get("PCOS_CONFIDENCE_THRESHOLD", "0.5"))
DEFAULT_MODEL = os.environ.get("PCOS_LLM_MODEL", "gpt-4o-mini")


@lru_cache(maxsize=1)
def load_env() -> None:
    """Load REPO_ROOT/.env into the environment once, if python-dotenv is present."""
    try:
        from dotenv import load_dotenv
    except Exception:
        return
    env_path = REPO_ROOT / ".env"
    if env_path.exists():
        load_dotenv(env_path)


def get_openai_api_key() -> str | None:
    load_env()
    return os.environ.get("OPENAI_API_KEY")


def _env_flag(name: str, default: bool = False) -> bool:
    load_env()
    val = os.environ.get(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


def use_mock_data() -> bool:
    """Whether the app should default to bundled mock inputs (USE_MOCK_DATA)."""
    return _env_flag("USE_MOCK_DATA", False)


def mock_data_files() -> list[Path]:
    """Sorted list of input files in ``mock_data/`` (xpt/csv/tsv/xlsx)."""
    if not MOCK_DATA_DIR.exists():
        return []
    return sorted(
        p for p in MOCK_DATA_DIR.iterdir()
        if p.is_file() and p.suffix.lower() in _INPUT_SUFFIXES
    )
