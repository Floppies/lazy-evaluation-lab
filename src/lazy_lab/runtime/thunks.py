
"""Immutable runtime representations for Call-by-Need thunks."""

from __future__ import annotations

from dataclasses import dataclass, field

from lazy_lab.core.nodes import CoreExpr

from .environment import Environment
from .heap import HeapObject
from .references import HeapReference
from .captures import select_free_local_names


@dataclass(frozen=True, slots=True, eq=False)
class ThunkPayload(HeapObject):
    """Deferred Core expression with captured local references.

    Global bindings are resolved separately when the thunk
    is evaluated. The Core AST is not counted per node in
    the simulated heap.
    """

    expression: CoreExpr = field(repr=False)
    captured_locals: Environment = field(repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.expression, CoreExpr):
            raise TypeError(
                "ThunkPayload requires a Core expression"
            )

        if not isinstance(self.captured_locals, Environment):
            raise TypeError(
                "captured_locals must be an Environment"
            )

        if self.captured_locals.parent is not None:
            raise ValueError(
                "captured_locals must be a standalone Environment"
            )

    @property
    def required_slots(self) -> int:
        return 1 + len(self.captured_locals.bindings)


@dataclass(frozen=True, slots=True)
class PendingThunk(HeapObject):
    """Stable thunk anchor awaiting its first demand."""

    payload_reference: HeapReference

    def __post_init__(self) -> None:
        if not isinstance(self.payload_reference, HeapReference):
            raise TypeError(
                "PendingThunk requires a heap payload reference"
            )

    @property
    def required_slots(self) -> int:
        return 1


@dataclass(frozen=True, slots=True)
class EvaluatingThunk(HeapObject):
    """Stable thunk anchor whose evaluation is in progress."""

    payload_reference: HeapReference

    def __post_init__(self) -> None:
        if not isinstance(self.payload_reference, HeapReference):
            raise TypeError(
                "EvaluatingThunk requires a heap payload reference"
            )

    @property
    def required_slots(self) -> int:
        return 1


def capture_thunk_payload(
    expression: CoreExpr,
    definition_environment: Environment,
    global_environment: Environment,
) -> ThunkPayload:
    """Build a deferred payload with minimal local captures.

    The expression is not evaluated or forced.

    Global and predefined references remain available through
    the global environment when evaluation starts.
    """
    free_local_names = select_free_local_names(
        expression,
        definition_environment,
        global_environment,
    )

    captures = {
        name: definition_environment.lookup(name)
        for name in free_local_names
    }

    return ThunkPayload(
        expression=expression,
        captured_locals=Environment(captures),
    )
