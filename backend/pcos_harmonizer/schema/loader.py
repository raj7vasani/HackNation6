"""Load the canonical schema JSON and expose a cached :class:`FieldRegistry`."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from ..config import SCHEMA_PATH
from .registry import FieldRegistry


def load_schema(path: Path | str | None = None) -> dict[str, Any]:
    schema_path = Path(path) if path else SCHEMA_PATH
    if not schema_path.exists():
        raise FileNotFoundError(f"Canonical schema not found: {schema_path}")
    with open(schema_path, encoding="utf-8") as fh:
        return json.load(fh)


@lru_cache(maxsize=1)
def get_registry() -> FieldRegistry:
    """Cached registry built from the default schema path."""
    return FieldRegistry(load_schema())


def load_registry(path: Path | str | None = None) -> FieldRegistry:
    """Build a registry from an explicit path (uncached)."""
    return FieldRegistry(load_schema(path))
