"""Deterministic derivations: arithmetic → criteria → diagnosis (strict order)."""

from .arithmetic import derive_arithmetic
from .criteria import derive_criteria
from .diagnosis import derive_diagnosis

__all__ = ["derive_arithmetic", "derive_criteria", "derive_diagnosis", "derive_all"]


def derive_all(df, insulin_unit: str | None = "pmol/L") -> list[str]:
    """Run derivations in order and return combined warnings."""
    warnings: list[str] = []
    warnings += derive_arithmetic(df, insulin_unit=insulin_unit)
    warnings += derive_criteria(df)
    warnings += derive_diagnosis(df)
    return warnings
