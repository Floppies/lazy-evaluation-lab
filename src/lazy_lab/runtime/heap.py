
"""Basic simulated heap objects and storage cells."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

from .references import HeapReference, ObjectId, RuntimeRef


class HeapObject:
    """Base class for simulated heap objects."""

    __slots__ = ()

    @property
    def required_slots(self) -> int:
        raise NotImplementedError(
            "Heap objects must declare required_slots"
        )


@dataclass(frozen=True, slots=True)
class Reserved(HeapObject):
    """An allocated cell awaiting initialization."""
    @property
    def required_slots(self) -> int:
        return 1


@dataclass(frozen=True, slots=True)
class Indirection(HeapObject):
    """A cell referring to another runtime reference."""

    target: RuntimeRef

    @property
    def required_slots(self) -> int:
        return 1


@dataclass(frozen=True, slots=True)
class HeapCell:
    object_id: ObjectId
    value: HeapObject
    allocated_slots: int


class InvalidHeapAddressError(LookupError):
    """Raised when a heap address does not exist."""


class Heap:
    """Mutable simulated heap with stable logical addresses."""

    def __init__(self) -> None:
        self._cells: dict[ObjectId, HeapCell] = {}
        self._next_object_id = 0
        self._current_slots = 0

    @property
    def next_object_id(self) -> int:
        return self._next_object_id

    @property
    def current_slots(self) -> int:
        return self._current_slots

    @property
    def cells(self) -> Mapping[ObjectId, HeapCell]:
        return MappingProxyType(self._cells)

    def allocate(
        self,
        value: HeapObject,
        *,
        allocated_slots: int,
    ) -> HeapReference:
        """Allocate a new cell and return its stable reference."""
        self._validate_object(value)

        if value.required_slots > allocated_slots:
            raise ValueError(
                "Heap object exceeds reserved allocation size"
            )

        if type(allocated_slots) is not int or allocated_slots < 1:
            raise ValueError(
                "allocated_slots must be a positive integer"
            )

        object_id = ObjectId(self._next_object_id)

        self._cells[object_id] = HeapCell(
            object_id=object_id,
            value=value,
            allocated_slots=allocated_slots,
        )

        self._next_object_id += 1
        self._current_slots += allocated_slots

        return HeapReference(object_id)

    def get(self, reference: HeapReference) -> HeapCell:
        """Read a cell without following indirections or forcing it."""
        if not isinstance(reference, HeapReference):
            raise TypeError("Expected a HeapReference")

        try:
            return self._cells[reference.object_id]
        except KeyError as exc:
            raise InvalidHeapAddressError(
                f"Unknown heap address: {reference.object_id}"
            ) from exc

    def replace(
        self,
        reference: HeapReference,
        value: HeapObject,
    ) -> None:
        """Replace a cell's contents while preserving its allocation."""
        self._validate_object(value)

        previous = self.get(reference)

        if value.required_slots > previous.allocated_slots:
            raise ValueError(
                "Replacement exceeds reserved allocation size"
            )

        self._cells[reference.object_id] = HeapCell(
            object_id=previous.object_id,
            value=value,
            allocated_slots=previous.allocated_slots,
        )

    def clone(self) -> Heap:
        """Return an independent copy of the heap state."""
        result = Heap()
        result._cells = self._cells.copy()
        result._next_object_id = self._next_object_id
        result._current_slots = self._current_slots
        return result

    @staticmethod
    def _validate_object(value: HeapObject) -> None:
        if not isinstance(value, HeapObject):
            raise TypeError("Expected a HeapObject")
