
"""In-memory retention of interactive execution snapshots."""

from __future__ import annotations

from dataclasses import dataclass, field

from lazy_lab.runtime.state import ExecutionState, TraceMode


class HistoryStateUnavailableError(LookupError):
    """The requested logical state was not retained."""


@dataclass(slots=True)
class HistoryStore:
    """Store independent snapshots for a single execution run."""

    session_id: str
    trace_mode: TraceMode

    _snapshots: dict[int, ExecutionState] = field(
        default_factory=dict,
        init=False,
        repr=False,
    )

    def __post_init__(self) -> None:
        if not isinstance(self.session_id, str) or not self.session_id:
            raise ValueError("Session ID must be a non-empty string")

        if not isinstance(self.trace_mode, TraceMode):
            raise TypeError("Expected a TraceMode")

    @property
    def available_indices(self) -> tuple[int, ...]:
        """Return retained logical indices in ascending order."""

        return tuple(sorted(self._snapshots))

    @property
    def snapshot_count(self) -> int:
        """Return the number of distinct retained states."""

        return len(self._snapshots)

    def retain(self, state: ExecutionState) -> bool:
        """Retain an explicitly requested state if the mode allows it.

        FULL callers retain the initial state and every transition.
        EVENTS callers retain only states chosen for capture windows.
        METRICS_ONLY never stores historical snapshots.

        Return True only when a new snapshot is stored.
        """
        if not isinstance(state, ExecutionState):
            raise TypeError("Expected an ExecutionState")

        if state.session_id != self.session_id:
            raise ValueError(
                "Cannot retain a state from another session"
            )

        if self.trace_mode is TraceMode.METRICS_ONLY:
            return False

        index = state.transition_index
        existing = self._snapshots.get(index)

        if existing is not None:
            if existing.state_id != state.state_id:
                raise ValueError(
                    "Conflicting state for transition index "
                    f"{index}"
                )

            # Overlapping windows reuse the first retained copy.
            return False

        self._snapshots[index] = state.snapshot()
        return True

    def get_snapshot(self, transition_index: int) -> ExecutionState:
        """Return an independent copy of a retained state."""

        if (
            type(transition_index) is not int
            or transition_index < 0
        ):
            raise ValueError(
                "Transition index must be a non-negative integer"
            )

        try:
            stored = self._snapshots[transition_index]
        except KeyError as exc:
            raise HistoryStateUnavailableError(
                "No retained state at transition index "
                f"{transition_index}"
            ) from exc

        return stored.snapshot()
