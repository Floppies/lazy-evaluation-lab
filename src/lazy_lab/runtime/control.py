
"""Structural controls for the Core abstract machine."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypeAlias

from lazy_lab.core.nodes import CoreBinding, CoreExpr

from .references import RuntimeRef


@dataclass(frozen=True, slots=True)
class EvaluateCore:
    expression: CoreExpr


@dataclass(frozen=True, slots=True)
class Return:
    reference: RuntimeRef


@dataclass(frozen=True, slots=True)
class Force:
    reference: RuntimeRef


@dataclass(frozen=True, slots=True)
class InitializeCoreBindings:
    bindings: tuple[CoreBinding, ...]
    next_index: int = 0
    entry_expression: CoreExpr | None = None
    scope_reserved: bool = False


@dataclass(frozen=True, slots=True)
class InitializeLocalBindings:
    """Initialize a reserved local recursive binding group."""

    bindings: tuple[CoreBinding, ...]
    body: CoreExpr
    next_index: int = 0


@dataclass(frozen=True, slots=True)
class ApplyPrimitive:
    """Primitive whose operands have all reached WHNF."""

    operator: str
    arguments: tuple[RuntimeRef, ...]


CoreControl: TypeAlias = (
    EvaluateCore
    | Return
    | Force
    | InitializeCoreBindings
    | InitializeLocalBindings
    | ApplyPrimitive 
)

