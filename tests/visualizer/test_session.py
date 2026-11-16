
"""Tests for interactive session initialization."""

import pytest

from lazy_lab.core.nodes import CoreProgram
from lazy_lab.semantics.name_resolution import NameResolutionError
from lazy_lab.runtime.state import (
    ExecutionConfig,
    ExecutionPhase,
    ExecutionStatus,
    MachineKind,
    ResultPolicy,
    Strategy,
    TraceMode,
)
from lazy_lab.visualizer.session import (
    InteractiveSession,
    create_interactive_session,
)


def make_config(
    strategy: Strategy = Strategy.CBNEED,
    *,
    machine_kind: MachineKind = MachineKind.CORE,
    trace_mode: TraceMode = TraceMode.FULL,
) -> ExecutionConfig:
    return ExecutionConfig(
        machine_kind=machine_kind,
        strategy=strategy,
        result_policy=ResultPolicy.ASK_AT_WHNF,
        execution_step_limit=100,
        result_node_limit=100,
        trace_mode=trace_mode,
    )


@pytest.mark.parametrize(
    "strategy",
    [Strategy.CBV, Strategy.CBNEED],
)
def test_create_session_initializes_without_execution(strategy):
    source = "main = 42"
    config = make_config(strategy)

    session = create_interactive_session(source, config)

    assert isinstance(session, InteractiveSession)
    assert isinstance(session.core_program, CoreProgram)

    assert session.source == source
    assert session.entry == "main"
    assert session.config is config

    assert session.live_state.session_id == session.session_id
    assert session.live_state.transition_index == 0
    assert session.live_state.state_id == 0
    assert session.read_cursor_index == 0

    machine = session.live_state.machine_state

    assert machine.strategy is strategy
    assert machine.phase is ExecutionPhase.INITIALIZATION
    assert machine.status is ExecutionStatus.RUNNING
    assert machine.evaluator_transition_count == 0
    assert machine.heap.current_slots == 0
    assert machine.stack.depth == 0


def test_sessions_have_independent_identities():
    config = make_config()

    first = create_interactive_session("main = 42", config)
    second = create_interactive_session("main = 42", config)

    assert first.session_id != second.session_id
    assert first.live_state is not second.live_state
    assert first.live_state.machine_state.heap is not (
        second.live_state.machine_state.heap
    )


def test_invalid_source_is_rejected():
    with pytest.raises(NameResolutionError, match="missing"):
        create_interactive_session(
            "main = missing",
            make_config(),
        )


def test_unknown_entry_is_rejected():
    with pytest.raises(ValueError, match="Unknown entry binding"):
        create_interactive_session(
            "main = 42",
            make_config(),
            entry="other",
        )


@pytest.mark.parametrize(
    ("machine_kind", "strategy"),
    [
        (MachineKind.CORE, Strategy.CBN),
        (MachineKind.STG, Strategy.CBNEED),
    ],
)
def test_unsupported_execution_modes_are_rejected(
    machine_kind,
    strategy,
):
    config = make_config(
        strategy,
        machine_kind=machine_kind,
    )

    with pytest.raises(
        ValueError,
        match="only Core CBV and CBNeed",
    ):
        create_interactive_session("main = 42", config)


def test_events_session_preserves_capture_categories():
    categories = frozenset({"thunks", "materialization"})

    session = create_interactive_session(
        "main = 42",
        make_config(trace_mode=TraceMode.EVENTS),
        capture_categories=categories,
    )

    assert session.capture_categories == categories
    assert session.config.trace_mode is TraceMode.EVENTS


def test_capture_filters_require_events_mode():
    with pytest.raises(
        ValueError,
        match="require EVENTS",
    ):
        create_interactive_session(
            "main = 42",
            make_config(trace_mode=TraceMode.FULL),
            capture_categories=frozenset({"thunks"}),
        )
