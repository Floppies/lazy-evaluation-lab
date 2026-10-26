
"""Runtime representations of predefined function values."""

from __future__ import annotations

from dataclasses import dataclass

from lazy_lab.semantics.predefined import (
    PREDEFINED_FUNCTION_ARITIES,
)

from .heap import HeapObject
from .references import (
    RuntimeRef,
    ImmediateInteger,
    ImmediateBoolean,
    HeapReference,
)


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


@dataclass(frozen=True, slots=True, eq=False)
class PartialPredefinedFunction(HeapObject):
    """A predefined function with some arguments already applied."""

    name: str
    applied_arguments: tuple[RuntimeRef, ...]

    def __post_init__(self) -> None:
        if self.name not in PREDEFINED_FUNCTION_ARITIES:
            raise ValueError(
                f"Unknown predefined function: {self.name!r}"
            )

        if not isinstance(self.applied_arguments, tuple):
            raise TypeError(
                "Applied arguments must be a tuple"
            )

        if not (
            0 < len(self.applied_arguments) < self.arity
        ):
            raise ValueError(
                "Partial application must have at least one "
                "argument and fewer arguments than its arity"
            )

        if not all(
            isinstance(
                reference,
                (ImmediateInteger, ImmediateBoolean, HeapReference),
            )
            for reference in self.applied_arguments
        ):
            raise TypeError(
                "Applied arguments must be runtime references"
            )

    @property
    def arity(self) -> int:
        return PREDEFINED_FUNCTION_ARITIES[self.name]

    @property
    def remaining_arity(self) -> int:
        return self.arity - len(self.applied_arguments)

    @property
    def required_slots(self) -> int:
        return 1 + len(self.applied_arguments)
