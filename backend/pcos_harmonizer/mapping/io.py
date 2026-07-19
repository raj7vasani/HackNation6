"""Read/write the mapping file as YAML."""

from __future__ import annotations

from pathlib import Path

import yaml

from .model import MappingFile


def write_mapping_file(mapping: MappingFile, path: Path | str) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = mapping.model_dump(mode="json")
    with open(path, "w", encoding="utf-8") as fh:
        yaml.safe_dump(data, fh, sort_keys=False, allow_unicode=True)
    return path


def read_mapping_file(path: Path | str) -> MappingFile:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Mapping file not found: {path}")
    with open(path, encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return MappingFile.model_validate(data)


def mapping_to_yaml(mapping: MappingFile) -> str:
    return yaml.safe_dump(mapping.model_dump(mode="json"), sort_keys=False, allow_unicode=True)
