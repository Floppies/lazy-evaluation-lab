
"""Selective event-window capture for interactive history."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

from lazy_lab.runtime.state import ExecutionState, TraceMode
from lazy_lab.runtime.transitions import TransitionResult
from lazy_lab.visualizer.capture import (
    matching_capture_categories,
    validate_capture_categories,
)
from lazy_lab.visualizer.history import HistoryStore


@dataclass(slots=True)
class EventWindowCapture:
    """Retain snapshots around matching execution transitions."""

    history: HistoryStore
    selected_categories: frozenset[str]

    _pending_successor_index: int | None = field(
        default=None,
        init=False,
        repr=False,
    )
    _last_observed_index: int | None = field(
        default=None,
        init=False,
        repr=False,
    )
    _reasons: dict[int, frozenset[str]] = field(
        default_factory=dict,
        init=False,
        repr=False,
    )

    def __post_init__(self) -> None:
        if not isinstance(self.history, HistoryStore):
            raise TypeError("Expected a HistoryStore")

        if self.history.trace_mode is not TraceMode.EVENTS:
            raise ValueError(
                "Event-window capture requires EVENTS trace mode"
            )

        validate_capture_categories(self.selected_categories)

    @property
    def captured_event_indices(self) -> tuple[int, ...]:
        """Return selected transition indices in ascending order."""
        return tuple(sorted(self._reasons))

    @property
    def capture_reasons(self) -> Mapping[int, frozenset[str]]:
        """Expose recorded matches without allowing mutation."""
        return MappingProxyType(self._reasons)

    @property
    def pending_successor_index(self) -> int | None:
        """Return the expected successor index, if any."""
        return self._pending_successor_index

    def update_categories(
        self,
        categories: frozenset[str],
    ) -> None:
        """Update filters for future observed transitions."""
        validate_capture_categories(categories)
        self.selected_categories = categories

    def observe_transition(
        self,
        previous_state: ExecutionState,
        transition: TransitionResult,
    ) -> frozenset[str]:
        """Capture snapshots around selected transitions.

        The callback is invoked after a successful transition.
        The following state of a matched event is retained when
        the next transition is observed.
        """
        if not isinstance(previous_state, ExecutionState):
            raise TypeError("Expected an ExecutionState")

        if not isinstance(transition, TransitionResult):
            raise TypeError("Expected a TransitionResult")

        next_state = transition.next_state
        next_index = next_state.transition_index

        if (
            previous_state.session_id != self.history.session_id
            or next_state.session_id != self.history.session_id
        ):
            raise ValueError(
                "Transition belongs to another session"
            )

        if (
            transition.previous_state_id != previous_state.state_id
            or next_index != previous_state.transition_index + 1
        ):
            raise ValueError(
                "Inconsistent observed transition"
            )

        if (
            self._last_observed_index is not None
            and previous_state.transition_index
            != self._last_observed_index
        ):
            raise ValueError(
                "Observed transitions must be consecutive"
            )

        matched = matching_capture_categories(
            transition,
            self.selected_categories,
        )

        # Complete the window opened by the preceding transition.
        if self._pending_successor_index is not None:
            if next_index != self._pending_successor_index:
                raise ValueError(
                    "Unexpected event-window successor index"
                )

            self.history.retain(next_state)
            self._pending_successor_index = None

        # Start a window for the current matching transition.
        if matched:
            self.history.retain(previous_state)
            self.history.retain(next_state)

            self._reasons[next_index] = matched
            self._pending_successor_index = next_index + 1

        self._last_observed_index = next_index
        return matched
