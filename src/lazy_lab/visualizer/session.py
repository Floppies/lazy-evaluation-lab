
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

    if not isinstance(capture_categories, frozenset):
        raise TypeError("Capture categories must be a frozenset")

    if any(
        type(category) is not str or not category
        for category in capture_categories
    ):
        raise ValueError("Invalid capture category")

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

    return InteractiveSession(
        session_id=session_id,
        source=source,
        core_program=core_program,
        config=config,
        entry=entry,
        capture_categories=capture_categories,
        live_state=initial_state,
        read_cursor_index=initial_state.transition_index,
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

def step_interactive_session(
    session: InteractiveSession,
) -> BatchResult:
    """Advance the live session by at most one logical transition."""

    return run_interactive_batch(session, max_steps=1)

def select_interactive_result_mode(
    session: InteractiveSession,
    selected_mode: ResultPolicy,
) -> TransitionResult:
    """Apply an explicit result-mode selection to the live head."""

    transition = select_result_mode(
        session.live_state,
        session.config,
        selected_mode,
    )

    _replace_live_state(session, transition.next_state)

    # Result selection does not implicitly resume automatic execution.
    session.auto_run_requested = False

    return transition

def run_interactive_batch(
    session: InteractiveSession,
    *,
    max_steps: int,
) -> BatchResult:
    """Run a bounded batch from the live execution state."""

    result = run_session_batch(
        session.live_state,
        session.config,
        max_steps=max_steps,
    )

    _replace_live_state(session, result.state)

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
