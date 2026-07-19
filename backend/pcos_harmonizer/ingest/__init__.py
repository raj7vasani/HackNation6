"""Ingestion: readers, multi-file join, longitudinal rejection."""

from .longitudinal import LongitudinalInputError, is_longitudinal, reject_if_longitudinal
from .multifile import JoinResult, detect_join_key, join_files
from .readers import IngestedFile, read_file, read_files

__all__ = [
    "IngestedFile",
    "JoinResult",
    "LongitudinalInputError",
    "detect_join_key",
    "is_longitudinal",
    "join_files",
    "read_file",
    "read_files",
    "reject_if_longitudinal",
]
