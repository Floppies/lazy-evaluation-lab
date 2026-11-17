
"""Interactive execution session initialization."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from lazy_lab.core.nodes import CoreProgram
from lazy_lab.engine.core_machine import create_initial_core_state
from lazy_lab.pipeline import compile_source
from lazy_lab.runtime.state import (
    ExecutionConfig,
    ExecutionState,
    ExecutionStatus,
    MachineKind,
    Strategy,
    TraceMode,
)
from lazy_lab.engine.session_runner import run_session_batch
from lazy_lab.engine.result_consumer import select_result_mode
from lazy_lab.runtime.state import ResultPolicy
from lazy_lab.runtime.transitions import BatchResult, BatchStopReason, TransitionResult
from lazy_lab.visualizer.capture import validate_capture_categories
from lazy_lab.visualizer.history import (
    HistoryStore,
    HistoryStateUnavailableError,
)
from lazy_lab.visualizer.windows import EventWindowCapture


@dataclass(slots=True)
class InteractiveSession:
    """Controller-owned state for a single execution run."""

    session_id: str
    source: str
    core_program: CoreProgram
    config: ExecutionConfig
    entry: str
    capture_categories: frozenset[str]
    live_state: ExecutionState
    read_cursor_index: int

    history: HistoryStore
    event_capture: EventWindowCapture | None = None
    auto_run_requested: bool = False


def create_interactive_session(
    source: str,
    config: ExecutionConfig,
    *,
    entry: str = "main",
    capture_categories: frozenset[str] = frozenset(),
) -> InteractiveSession:
    """Compile a program and create a session without executing it."""

    if not isinstance(source, str):
        raise TypeError("Source must be a string")

    if not isinstance(config, ExecutionConfig):
        raise TypeError("Expected an ExecutionConfig")

    if (
        config.machine_kind is not MachineKind.CORE
        or config.strategy not in (Strategy.CBV, Strategy.CBNEED)
    ):
        raise ValueError(
            "Interactive sessions support only Core CBV and CBNeed"
        )

    if not isinstance(entry, str):
        raise TypeError("Entry must be a binding name")

    if not entry:
        raise ValueError("Entry must not be empty")

    validate_capture_categories(capture_categories)

    if (
        config.trace_mode is not TraceMode.EVENTS
        and capture_categories
    ):
        raise ValueError(
            "Capture categories require EVENTS trace mode"
        )

    core_program = compile_source(source)
    session_id = uuid4().hex

    initial_state = create_initial_core_state(
        core_program,
        config,
        session_id=session_id,
        entry=entry,
    )

    history = HistoryStore(
        session_id=session_id,
        trace_mode=config.trace_mode,
    )

    if config.trace_mode is TraceMode.FULL:
        history.retain(initial_state)

    event_capture = (
        EventWindowCapture(
            history=history,
            selected_categories=capture_categories,
        )
        if config.trace_mode is TraceMode.EVENTS
        else None
    )

    return InteractiveSession(
        session_id=session_id,
        source=source,
        core_program=core_program,
        config=config,
        entry=entry,
        capture_categories=capture_categories,
        live_state=initial_state,
        read_cursor_index=initial_state.transition_index,
        history=history,
        event_capture=event_capture,
    )

def _replace_live_state(
    session: InteractiveSession,
    next_state: ExecutionState,
) -> None:
    """Replace the live head while preserving cursor semantics."""

    was_following = (
        session.read_cursor_index
        == session.live_state.transition_index
    )

    session.live_state = next_state

    if (
        was_following
        or session.config.trace_mode is TraceMode.METRICS_ONLY
    ):
        session.read_cursor_index = next_state.transition_index

def _observe_session_transition(
    session: InteractiveSession,
    previous_state: ExecutionState,
    transition: TransitionResult,
) -> None:
    """Record a successful transition and advance the live head."""

    if previous_state is not session.live_state:
        raise RuntimeError(
            "Observed transition does not start at the live head"
        )

    if session.config.trace_mode is TraceMode.FULL:
        session.history.retain(transition.next_state)

    elif session.config.trace_mode is TraceMode.EVENTS:
        assert session.event_capture is not None

        session.event_capture.observe_transition(
            previous_state,
            transition,
        )

    _replace_live_state(
        session,
        transition.next_state,
    )

def step_interactive_session(
    session: InteractiveSession,
) -> BatchResult:
    """Advance the live session by at most one logical transition."""

    return run_interactive_batch(session, max_steps=1)

def select_interactive_result_mode(
    session: InteractiveSession,
    selected_mode: ResultPolicy,
) -> TransitionResult:
    """Apply and record an explicit result-mode selection."""

    previous_state = session.live_state

    transition = select_result_mode(
        previous_state,
        session.config,
        selected_mode,
    )

    _observe_session_transition(
        session,
        previous_state,
        transition,
    )

    # A result-mode selection never resumes automatic execution.
    session.auto_run_requested = False

    return transition

def run_interactive_batch(
    session: InteractiveSession,
    *,
    max_steps: int,
) -> BatchResult:
    """Execute a bounded batch with session history observation."""

    result = run_session_batch(
        session.live_state,
        session.config,
        max_steps=max_steps,
        on_transition=lambda previous, transition: (
            _observe_session_transition(
                session,
                previous,
                transition,
            )
        ),
    )

    if (
        result.stop_reason in (
            BatchStopReason.WHNF_PENDING,
            BatchStopReason.EVALUATOR_BUDGET,
            BatchStopReason.TERMINAL_STATUS,
        )
        or result.state.machine_state.status
        is not ExecutionStatus.RUNNING
    ):
        session.auto_run_requested = False

    return result

def request_auto_run(
    session: InteractiveSession,
) -> None:
    """Allow the client to request successive bounded batches."""

    if (
        session.live_state.machine_state.status
        is not ExecutionStatus.RUNNING
    ):
        raise ValueError(
            "Cannot start automatic execution of a terminal session"
        )

    session.auto_run_requested = True

def pause_interactive_session(
    session: InteractiveSession,
) -> None:
    """Stop automatic batch requests without changing machine state."""

    session.auto_run_requested = False

def reset_interactive_session(
    session: InteractiveSession,
) -> InteractiveSession:
    """Create a fresh run with the same program and configuration."""

    return create_interactive_session(
        session.source,
        session.config,
        entry=session.entry,
        capture_categories=session.capture_categories,
    )

def available_session_indices(
    session: InteractiveSession,
) -> tuple[int, ...]:
    """List retained indices together with the live-head index."""

    return tuple(sorted({
        *session.history.available_indices,
        session.live_state.transition_index,
    }))

def get_inspected_state(
    session: InteractiveSession,
) -> ExecutionState:
    """Return a passive copy of the state selected by the cursor."""

    if (
        session.read_cursor_index
        == session.live_state.transition_index
    ):
        return session.live_state.snapshot()

    return session.history.get_snapshot(
        session.read_cursor_index
    )

def select_historical_state(
    session: InteractiveSession,
    transition_index: int,
) -> ExecutionState:
    """Move the read cursor only when the requested state exists."""

    if (
        type(transition_index) is not int
        or transition_index < 0
    ):
        raise ValueError(
            "Transition index must be a non-negative integer"
        )

    if transition_index == session.live_state.transition_index:
        state = session.live_state.snapshot()
    else:
        state = session.history.get_snapshot(transition_index)

    session.read_cursor_index = transition_index
    return state

def follow_live_head(
    session: InteractiveSession,
) -> ExecutionState:
    """Return the read cursor to the current live execution state."""

    session.read_cursor_index = (
        session.live_state.transition_index
    )

    return session.live_state.snapshot()

def update_interactive_capture_categories(
    session: InteractiveSession,
    categories: frozenset[str],
) -> None:
    """Change EVENTS filters for future transitions only."""

    if session.config.trace_mode is not TraceMode.EVENTS:
        raise ValueError(
            "Capture filters require EVENTS trace mode"
        )

    if session.auto_run_requested:
        raise RuntimeError(
            "Pause automatic execution before updating filters"
        )

    assert session.event_capture is not None

    session.event_capture.update_categories(categories)
    session.capture_categories = categories
