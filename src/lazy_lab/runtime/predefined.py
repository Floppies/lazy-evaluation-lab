
"""Runtime representations of predefined function values."""

from __future__ import annotations

from dataclasses import dataclass

from lazy_lab.semantics.predefined import (
    PREDEFINED_FUNCTION_ARITIES,
)

from .heap import HeapObject


@dataclass(frozen=True, slots=True, eq=False)
class PredefinedFunction(HeapObject):
    """An unapplied predefined function value."""

    name: str

    def __post_init__(self) -> None:
        if self.name not in PREDEFINED_FUNCTION_ARITIES:
            raise ValueError(
                f"Unknown predefined function: {self.name!r}"
            )

    @property
    def arity(self) -> int:
        return PREDEFINED_FUNCTION_ARITIES[self.name]

    @property
    def required_slots(self) -> int:
        return 1
