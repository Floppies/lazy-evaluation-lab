
"""Structural fingerprints for deterministic runtime tests."""

from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from enum import Enum

from lazy_lab.runtime.heap import Heap
from lazy_lab.runtime.stack import Stack


def runtime_fingerprint(value):
    """Normalize runtime state without comparing Python identities."""

    if isinstance(value, Heap):
        return (
            "Heap",
            value.next_object_id,
            value.current_slots,
            tuple(
                (
                    int(object_id),
                    runtime_fingerprint(cell),
                )
                for object_id, cell in sorted(
                    value.cells.items(),
                    key=lambda item: int(item[0]),
                )
            ),
        )

    if isinstance(value, Stack):
        return (
            "Stack",
            tuple(
                runtime_fingerprint(frame)
                for frame in value.frames
            ),
        )

    if isinstance(value, Enum):
        return (
            type(value).__qualname__,
            value.value,
        )

    if is_dataclass(value) and not isinstance(value, type):
        return (
            type(value).__qualname__,
            tuple(
                (
                    field.name,
                    runtime_fingerprint(
                        getattr(value, field.name)
                    ),
                )
                for field in fields(value)
            ),
        )

    if isinstance(value, Mapping):
        entries = (
            (
                runtime_fingerprint(key),
                runtime_fingerprint(item),
            )
            for key, item in value.items()
        )

        return tuple(
            sorted(entries, key=lambda entry: repr(entry[0]))
        )

    if isinstance(value, (tuple, list)):
        return tuple(
            runtime_fingerprint(item)
            for item in value
        )

    if value is None or type(value) in (
        str, int, float, bool
    ):
        return value

    raise TypeError(
        f"Unsupported fingerprint type: {type(value).__name__}"
    )
