
"""Tests for selective event-window capture."""

from dataclasses import replace

import pytest

from lazy_lab.metrics.effects import HeapAllocated
from lazy_lab.metrics.events import (
    SemanticEvent,
    SemanticEventKind,
)
from lazy_lab.runtime.references import ObjectId
from lazy_lab.runtime.state import (
    ExecutionConfig,
    MachineKind,
    ResultPolicy,
    Strategy,
    TraceMode,
)
from lazy_lab.runtime.transitions import (
    RuleId,
    TransitionKind,
    TransitionResult,
)
from lazy_lab.visualizer.history import HistoryStore
from lazy_lab.visualizer.session import create_interactive_session
from lazy_lab.visualizer.windows import EventWindowCapture


def make_session(trace_mode=TraceMode.EVENTS):
    config = ExecutionConfig(
        machine_kind=MachineKind.CORE,
        strategy=Strategy.CBNEED,
        result_policy=ResultPolicy.WHNF_ONLY,
        execution_step_limit=100,
        result_node_limit=100,
        trace_mode=trace_mode,
    )
    return create_interactive_session("main = 42", config)


def make_capture(*categories):
    session = make_session()
    history = HistoryStore(
        session_id=session.session_id,
        trace_mode=session.config.trace_mode,
    )
    capture = EventWindowCapture(
        history=history,
        selected_categories=frozenset(categories),
    )
    return session.live_state, history, capture


def make_transition(
    previous,
    *,
    events=(),
    heap_effects=(),
):
    successor = replace(
        previous.snapshot(),
        state_id=previous.state_id + 1,
        transition_index=previous.transition_index + 1,
    )
    transition = TransitionResult(
        previous_state_id=previous.state_id,
        next_state=successor,
        rule_id=RuleId.CORE_EVAL_INTEGER,
        transition_kind=TransitionKind.EVALUATOR,
        phase_before=previous.machine_state.phase,
        phase_after=successor.machine_state.phase,
        semantic_events=tuple(
            SemanticEvent(kind) for kind in events
        ),
        heap_effects=heap_effects,
    )
    return successor, transition


def test_matching_event_opens_window():
    state0, history, capture = make_capture("thunks")

    state1, transition = make_transition(
        state0,
        events=(SemanticEventKind.THUNK_UPDATED,),
    )

    matched = capture.observe_transition(state0, transition)

    assert matched == frozenset({"thunks"})
    assert history.available_indices == (0, 1)
    assert capture.pending_successor_index == 2

    assert capture.captured_event_indices == (1,)
    assert capture.capture_reasons[1] == frozenset({"thunks"})


def test_following_transition_completes_window():
    state0, history, capture = make_capture("thunks")

    state1, first = make_transition(
        state0,
        events=(SemanticEventKind.THUNK_UPDATED,),
    )
    capture.observe_transition(state0, first)

    state2, second = make_transition(state1)
    matched = capture.observe_transition(state1, second)

    assert matched == frozenset()
    assert history.available_indices == (0, 1, 2)
    assert capture.pending_successor_index is None

    assert history.get_snapshot(2).state_id == state2.state_id


def test_unselected_transitions_are_not_retained():
    state0, history, capture = make_capture("thunks")

    state1, first = make_transition(state0)
    capture.observe_transition(state0, first)

    state2, second = make_transition(
        state1,
        events=(SemanticEventKind.THUNK_CREATED,),
    )
    capture.observe_transition(state1, second)

    state3, third = make_transition(state2)
    capture.observe_transition(state2, third)

    assert history.available_indices == (1, 2, 3)
    assert history.snapshot_count == 3
    assert capture.captured_event_indices == (2,)


def test_consecutive_events_share_snapshots():
    state0, history, capture = make_capture("thunks")

    state1, first = make_transition(
        state0,
        events=(SemanticEventKind.THUNK_CREATED,),
    )
    capture.observe_transition(state0, first)

    state2, second = make_transition(
        state1,
        events=(SemanticEventKind.THUNK_DEMANDED,),
    )
    capture.observe_transition(state1, second)

    state3, third = make_transition(state2)
    capture.observe_transition(state2, third)

    assert history.available_indices == (0, 1, 2, 3)
    assert history.snapshot_count == 4
    assert capture.captured_event_indices == (1, 2)
    assert capture.pending_successor_index is None


def test_final_event_keeps_incomplete_window():
    state0, history, capture = make_capture("thunks")

    state1, transition = make_transition(
        state0,
        events=(SemanticEventKind.THUNK_UPDATED,),
    )
    capture.observe_transition(state0, transition)

    # No later transition occurs.
    assert history.available_indices == (0, 1)
    assert capture.pending_successor_index == 2
    assert capture.captured_event_indices == (1,)


def test_transition_can_have_multiple_capture_reasons():
    state0, history, capture = make_capture("thunks", "heap")

    state1, transition = make_transition(
        state0,
        events=(SemanticEventKind.THUNK_CREATED,),
        heap_effects=(
            HeapAllocated(
                object_id=ObjectId(0),
                allocated_slots=1,
                object_type="PendingThunk",
            ),
        ),
    )

    result = capture.observe_transition(state0, transition)

    assert result == frozenset({"thunks", "heap"})
    assert capture.capture_reasons[1] == result
    assert history.snapshot_count == 2


def test_filter_changes_only_affect_future_matches():
    state0, history, capture = make_capture("thunks")

    state1, first = make_transition(
        state0,
        events=(SemanticEventKind.THUNK_CREATED,),
    )
    capture.observe_transition(state0, first)

    capture.update_categories(frozenset({"heap"}))

    state2, second = make_transition(
        state1,
        events=(SemanticEventKind.THUNK_UPDATED,),
    )
    capture.observe_transition(state1, second)

    assert capture.captured_event_indices == (1,)
    assert history.available_indices == (0, 1, 2)

    state3, third = make_transition(
        state2,
        heap_effects=(
            HeapAllocated(
                object_id=ObjectId(1),
                allocated_slots=1,
                object_type="Reserved",
            ),
        ),
    )
    capture.observe_transition(state2, third)

    assert capture.captured_event_indices == (1, 3)
    assert capture.capture_reasons[1] == frozenset({"thunks"})
    assert capture.capture_reasons[3] == frozenset({"heap"})


def test_no_selected_categories_means_no_capture():
    state0, history, capture = make_capture()

    state1, transition = make_transition(
        state0,
        events=(SemanticEventKind.THUNK_CREATED,),
    )

    assert capture.observe_transition(
        state0, transition
    ) == frozenset()

    assert history.snapshot_count == 0
    assert capture.captured_event_indices == ()


def test_rejects_nonconsecutive_observation():
    state0, history, capture = make_capture("thunks")

    state1, first = make_transition(
        state0,
        events=(SemanticEventKind.THUNK_CREATED,),
    )
    capture.observe_transition(state0, first)

    state2, _ = make_transition(state1)
    _, skipped = make_transition(state2)

    with pytest.raises(
        ValueError,
        match="must be consecutive",
    ):
        capture.observe_transition(state2, skipped)

    assert history.available_indices == (0, 1)


def test_capture_requires_events_mode():
    session = make_session(TraceMode.FULL)
    history = HistoryStore(
        session_id=session.session_id,
        trace_mode=TraceMode.FULL,
    )

    with pytest.raises(
        ValueError,
        match="requires EVENTS",
    ):
        EventWindowCapture(
            history=history,
            selected_categories=frozenset({"thunks"}),
        )


def test_capture_rejects_other_session():
    state0, history, capture = make_capture("thunks")
    other = make_session()

    _, transition = make_transition(
        other.live_state,
        events=(SemanticEventKind.THUNK_CREATED,),
    )

    with pytest.raises(
        ValueError,
        match="another session",
    ):
        capture.observe_transition(
            other.live_state,
            transition,
        )

    assert history.snapshot_count == 0


def test_capture_reasons_are_read_only():
    state0, _, capture = make_capture("thunks")

    _, transition = make_transition(
        state0,
        events=(SemanticEventKind.THUNK_CREATED,),
    )
    capture.observe_transition(state0, transition)

    with pytest.raises(TypeError):
        capture.capture_reasons[1] = frozenset()
