
"""Per-transition collection of semantic events."""

from __future__ import annotations

from lazy_lab.core.nodes import CoreNode
from lazy_lab.runtime.references import ObjectId
from lazy_lab.source import OriginKind

from .events import (
    EventOrigin,
    SemanticEvent,
    SemanticEventKind,
)


class SemanticEventRecorder:
    """Collect events produced by one machine transition."""

    __slots__ = ("_events",)

    def __init__(self) -> None:
        self._events: list[SemanticEvent] = []

    def emit(
        self,
        kind: SemanticEventKind,
        *,
        node: CoreNode | None = None,
        object_id: ObjectId | None = None,
    ) -> None:
        if node is None:
            origin = EventOrigin(
                kind=OriginKind.UNKNOWN,
            )
        else:
            origin = EventOrigin(
                kind=node.origin,
                source_spans=(
                    (node.span,)
                    if node.span is not None
                    else ()
                ),
            )

        self._events.append(
            SemanticEvent(
                kind=kind,
                origin=origin,
                object_id=object_id,
            )
        )

    def freeze(self) -> tuple[SemanticEvent, ...]:
        """Return an immutable snapshot of recorded events."""
        return tuple(self._events)
