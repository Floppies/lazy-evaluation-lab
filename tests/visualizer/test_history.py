
"""Tests for in-memory execution history retention."""

from dataclasses import replace

import pytest

from lazy_lab.engine.core_machine import step
from lazy_lab.runtime.heap import Reserved
from lazy_lab.runtime.state import (
    ExecutionConfig,
    MachineKind,
    ResultPolicy,
    Strategy,
    TraceMode,
)
from lazy_lab.visualizer.history import (
    HistoryStateUnavailableError,
    HistoryStore,
)
from lazy_lab.visualizer.session import create_interactive_session


def make_session(trace_mode=TraceMode.FULL):
    config = ExecutionConfig(
        machine_kind=MachineKind.CORE,
        strategy=Strategy.CBNEED,
        result_policy=ResultPolicy.WHNF_ONLY,
        execution_step_limit=100,
        result_node_limit=100,
        trace_mode=trace_mode,
    )

    return create_interactive_session("main = 42", config)


def make_store(session):
    return HistoryStore(
        session_id=session.session_id,
        trace_mode=session.config.trace_mode,
    )


def advance(state, config):
    return step(state, config).next_state


def test_full_mode_retains_requested_states():
    session = make_session()
    store = make_store(session)

    initial = session.live_state
    first = advance(initial, session.config)
    second = advance(first, session.config)

    assert store.retain(initial)
    assert store.retain(first)
    assert store.retain(second)

    assert store.available_indices == (0, 1, 2)
    assert store.snapshot_count == 3

    assert store.get_snapshot(0).state_id == initial.state_id
    assert store.get_snapshot(1).state_id == first.state_id
    assert store.get_snapshot(2).state_id == second.state_id


def test_events_mode_retains_only_selected_states():
    session = make_session(TraceMode.EVENTS)
    store = make_store(session)

    initial = session.live_state
    first = advance(initial, session.config)
    second = advance(first, session.config)

    # The store does not automatically retain every transition.
    assert store.available_indices == ()

    assert store.retain(initial)
    assert store.retain(second)

    assert store.available_indices == (0, 2)

    with pytest.raises(HistoryStateUnavailableError):
        store.get_snapshot(1)


def test_metrics_only_does_not_store_snapshots():
    session = make_session(TraceMode.METRICS_ONLY)
    store = make_store(session)

    assert not store.retain(session.live_state)

    assert store.snapshot_count == 0
    assert store.available_indices == ()

    with pytest.raises(HistoryStateUnavailableError):
        store.get_snapshot(0)

    # The live state remains available through the controller.
    assert session.live_state.transition_index == 0


def test_duplicate_retention_is_idempotent():
    session = make_session()
    store = make_store(session)

    state = session.live_state

    assert store.retain(state)
    assert not store.retain(state)

    assert store.snapshot_count == 1
    assert store.available_indices == (0,)


def test_rejects_states_from_another_session():
    first_session = make_session()
    second_session = make_session()

    store = make_store(first_session)

    with pytest.raises(ValueError, match="another session"):
        store.retain(second_session.live_state)

    assert store.snapshot_count == 0


def test_rejects_conflicting_state_at_same_index():
    session = make_session()
    store = make_store(session)

    initial = session.live_state
    store.retain(initial)

    conflicting = replace(
        initial,
        state_id=initial.state_id + 100,
    )

    with pytest.raises(ValueError, match="Conflicting state"):
        store.retain(conflicting)

    assert store.snapshot_count == 1
    assert store.get_snapshot(0).state_id == initial.state_id


def test_snapshot_is_independent_of_original_heap():
    session = make_session()
    store = make_store(session)

    initial = session.live_state
    assert store.retain(initial)

    # Simulate a change to the caller-owned heap after retention.
    initial.machine_state.heap.allocate(
        Reserved(),
        allocated_slots=1,
    )

    retained = store.get_snapshot(0)

    assert initial.machine_state.heap.current_slots == 1
    assert retained.machine_state.heap.current_slots == 0


def test_returned_snapshot_cannot_mutate_stored_heap():
    session = make_session()
    store = make_store(session)

    store.retain(session.live_state)

    inspected = store.get_snapshot(0)

    inspected.machine_state.heap.allocate(
        Reserved(),
        allocated_slots=1,
    )

    stored_again = store.get_snapshot(0)

    assert inspected.machine_state.heap.current_slots == 1
    assert stored_again.machine_state.heap.current_slots == 0
    assert session.live_state.machine_state.heap.current_slots == 0

    assert inspected is not stored_again
    assert (
        inspected.machine_state.heap
        is not stored_again.machine_state.heap
    )


@pytest.mark.parametrize("index", [-1, True, "0", 0.5])
def test_rejects_invalid_transition_indices(index):
    session = make_session()
    store = make_store(session)

    with pytest.raises(ValueError, match="Transition index"):
        store.get_snapshot(index)


def test_unavailable_index_is_not_reconstructed():
    session = make_session()
    store = make_store(session)

    initial = session.live_state
    first = advance(initial, session.config)
    second = advance(first, session.config)

    store.retain(initial)
    store.retain(second)

    with pytest.raises(
        HistoryStateUnavailableError,
        match="transition index 1",
    ):
        store.get_snapshot(1)

    assert store.available_indices == (0, 2)
