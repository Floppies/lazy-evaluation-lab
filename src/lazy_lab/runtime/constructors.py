"""Immutable runtime representation of list constructors."""

from __future__ import annotations

from dataclasses import dataclass

from .heap import HeapObject
from .references import (
    RuntimeRef,
    ImmediateInteger,
    ImmediateBoolean,
    HeapReference,
)


_CONSTRUCTOR_ARITIES = {
    "Nil": 0,
    "Cons": 2,
}


@dataclass(frozen=True, slots=True, eq=False)
class ConstructorValue(HeapObject):
    tag: str
    fields: tuple[RuntimeRef, ...]

    def __post_init__(self) -> None:
        if type(self.tag) is not str:
            raise TypeError("Constructor tag must be a string")

        if self.tag not in _CONSTRUCTOR_ARITIES:
            raise ValueError(
                f"Unsupported runtime constructor: {self.tag!r}"
            )

        if not isinstance(self.fields, tuple):
            raise TypeError("Constructor fields must be a tuple")

        expected_arity = _CONSTRUCTOR_ARITIES[self.tag]

        if len(self.fields) != expected_arity:
            raise ValueError(
                f"Constructor {self.tag} expects "
                f"{expected_arity} fields, "
                f"got {len(self.fields)}"
            )

        for field in self.fields:
            if not isinstance(
                field,
                (
                    ImmediateInteger,
                    ImmediateBoolean,
                    HeapReference,
                ),
            ):
                raise TypeError(
                    "Constructor fields must be RuntimeRef values"
                )

    @property
    def required_slots(self) -> int:
        return 1 + len(self.fields)