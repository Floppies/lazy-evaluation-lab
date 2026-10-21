
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


CoreControl: TypeAlias = (
    EvaluateCore | Return | Force | InitializeCoreBindings
)
