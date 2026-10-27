
"""Canonical, passive observation of evaluated runtime values."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypeAlias

from .closures import Closure
from .global_bindings import PendingGlobal
from .heap import Heap, Indirection, Reserved
from .predefined import (
    PredefinedFunction,
    PartialPredefinedFunction,
)
from .references import (
    RuntimeRef,
    ImmediateInteger,
    ImmediateBoolean,
    HeapReference,
)


@dataclass(frozen=True, slots=True)
class CanonicalInteger:
    value: int


@dataclass(frozen=True, slots=True)
class CanonicalBoolean:
    value: bool


@dataclass(frozen=True, slots=True, eq=False)
class OpaqueFunction:
    """A function value without exposed runtime identity."""


CanonicalValue: TypeAlias = (
    CanonicalInteger
    | CanonicalBoolean
    | OpaqueFunction
)


class UnresolvedObservationError(ValueError):
    """The reference has not reached an observable WHNF."""


class UnsupportedObservationError(NotImplementedError):
    """The runtime value has no canonical representation yet."""


def observe_whnf(
    heap: Heap,
    reference: RuntimeRef,
) -> CanonicalValue:
    """Convert an already-WHNF reference without executing it."""
    if not isinstance(heap, Heap):
        raise TypeError("Expected a Heap")

    if isinstance(reference, ImmediateInteger):
        return CanonicalInteger(reference.value)

    if isinstance(reference, ImmediateBoolean):
        return CanonicalBoolean(reference.value)

    if not isinstance(reference, HeapReference):
        raise TypeError("Expected a RuntimeRef")

    value = heap.get(reference).value

    if isinstance(
        value,
        (
            Closure,
            PredefinedFunction,
            PartialPredefinedFunction,
        ),
    ):
        return OpaqueFunction()

    if isinstance(
        value,
        (Reserved, PendingGlobal, Indirection),
    ):
        raise UnresolvedObservationError(
            f"{type(value).__name__} has not reached WHNF"
        )

    raise UnsupportedObservationError(
        f"Cannot observe {type(value).__name__}"
    )
