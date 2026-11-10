
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
from .thunks import PendingThunk, EvaluatingThunk
from .constructors import ConstructorValue


@dataclass(frozen=True, slots=True)
class CanonicalInteger:
    value: int


@dataclass(frozen=True, slots=True)
class CanonicalBoolean:
    value: bool


@dataclass(frozen=True, slots=True, eq=False)
class OpaqueFunction:
    """A function value without exposed runtime identity."""


@dataclass(frozen=True, slots=True)
class ConstructorWHNF:
    """Canonical observation of a constructor in WHNF."""

    tag: str
    arity: int


@dataclass(frozen=True, slots=True)
class CanonicalConstructor:
    """A constructor whose fields are fully materialized."""

    tag: str
    fields: tuple[CanonicalValue, ...]


CanonicalValue: TypeAlias = (
    CanonicalInteger
    | CanonicalBoolean
    | OpaqueFunction
    | ConstructorWHNF
    | CanonicalConstructor
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

    if isinstance(value, ConstructorValue):
        return ConstructorWHNF(
            tag=value.tag,
            arity=len(value.fields),
        )

    if isinstance(
        value,
        (
            Reserved,
            PendingGlobal,
            Indirection,
            PendingThunk,
            EvaluatingThunk,
        ),
    ):
        raise UnresolvedObservationError(
            f"{type(value).__name__} has not reached WHNF"
        )

    raise UnsupportedObservationError(
        f"Cannot observe {type(value).__name__}"
    )
