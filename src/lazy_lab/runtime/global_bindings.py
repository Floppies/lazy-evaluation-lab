"""Runtime representations for demand-driven global bindings."""

from __future__ import annotations

from dataclasses import dataclass

from lazy_lab.core.nodes import CoreExpr

from .heap import HeapObject


@dataclass(frozen=True, slots=True, eq=False)
class PendingGlobal(HeapObject):
    """A global RHS installed but not yet evaluated.

    The evaluator determines how demands behave according to the
    configured strategy. This object does not implement caching,
    forcing, or updates.
    """

    expression: CoreExpr

    def __post_init__(self) -> None:
        if not isinstance(self.expression, CoreExpr):
            raise TypeError(
                "PendingGlobal requires a Core expression"
            )

    @property
    def required_slots(self) -> int:
        return 1
