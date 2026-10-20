
"""References to immediate values or objects in the simulated heap."""

from __future__ import annotations

from dataclasses import dataclass
from typing import NewType, TypeAlias


ObjectId = NewType("ObjectId", int)


@dataclass(frozen=True, slots=True)
class ImmediateInteger:
    value: int

    def __post_init__(self) -> None:
        if type(self.value) is not int:
            raise TypeError("ImmediateInteger requires an int")


@dataclass(frozen=True, slots=True)
class ImmediateBoolean:
    value: bool

    def __post_init__(self) -> None:
        if type(self.value) is not bool:
            raise TypeError("ImmediateBoolean requires a bool")


@dataclass(frozen=True, slots=True)
class HeapReference:
    object_id: ObjectId

    def __post_init__(self) -> None:
        if type(self.object_id) is not int or self.object_id < 0:
            raise ValueError("ObjectId must be a non-negative integer")


RuntimeRef: TypeAlias = (
    ImmediateInteger | ImmediateBoolean | HeapReference
)
