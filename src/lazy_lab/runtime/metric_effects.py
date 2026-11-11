
"""Typed heap and stack effects for metric accounting."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TypeAlias

from .metric_events import EventOrigin
from .references import ObjectId


@dataclass(frozen=True, slots=True)
class HeapAllocated:
    object_id: ObjectId
    allocated_slots: int
    object_type: str
    origin: EventOrigin = field(
        default_factory=EventOrigin
    )


@dataclass(frozen=True, slots=True)
class HeapReplaced:
    object_id: ObjectId
    previous_object_type: str
    new_object_type: str


@dataclass(frozen=True, slots=True)
class HeapBaselineRecorded:
    slots: int


HeapEffect: TypeAlias = (
    HeapAllocated
    | HeapReplaced
    | HeapBaselineRecorded
)


@dataclass(frozen=True, slots=True)
class StackPushed:
    frame_type: str


@dataclass(frozen=True, slots=True)
class StackPopped:
    frame_type: str


StackEffect: TypeAlias = StackPushed | StackPopped
