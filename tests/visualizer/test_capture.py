
"""Tests for pure event capture classification."""

from dataclasses import replace

import pytest

from lazy_lab.engine.core_machine import create_initial_core_state
from lazy_lab.metrics.effects import (
    HeapAllocated,
    HeapBaselineRecorded,
    HeapReplaced,
    StackPopped,
    StackPushed,
)
from lazy_lab.metrics.events import (
    SemanticEvent,
    SemanticEventKind,
)
from lazy_lab.pipeline import compile_source
from lazy_lab.runtime.references import ObjectId
from lazy_lab.runtime.state import (
    ExecutionConfig,
    ExecutionPhase,
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
from lazy_lab.visualizer.capture import (
    REDUCTION_EVENTS,
    SUPPORTED_CAPTURE_CATEGORIES,
    THUNK_EVENTS,
    matching_capture_categories,
    validate_capture_categories,
)
from lazy_lab.visualizer.session import create_interactive_session


@pytest.fixture
def initial_state():
    config = ExecutionConfig(
        machine_kind=MachineKind.CORE,
        strategy=Strategy.CBNEED,
        result_policy=ResultPolicy.WHNF_ONLY,
        execution_step_limit=100,
        result_node_limit=100,
        trace_mode=TraceMode.EVENTS,
    )

    return create_initial_core_state(
        compile_source("main = 42"),
        config,
        session_id="capture-test",
    )


def make_transition(
    initial_state,
    *,
    semantic_events=(),
    heap_effects=(),
    stack_effects=(),
    phase_before=ExecutionPhase.EVALUATION,
    phase_after=ExecutionPhase.EVALUATION,
    rule_id=RuleId.CORE_EVAL_INTEGER,
):
    next_machine = replace(
        initial_state.machine_state,
        phase=phase_after,
    )

    next_state = replace(
        initial_state,
        state_id=initial_state.state_id + 1,
        transition_index=initial_state.transition_index + 1,
        machine_state=next_machine,
    )

    return TransitionResult(
        previous_state_id=initial_state.state_id,
        next_state=next_state,
        rule_id=rule_id,
        transition_kind=TransitionKind.EVALUATOR,
        phase_before=phase_before,
        phase_after=phase_after,
        semantic_events=semantic_events,
        heap_effects=heap_effects,
        stack_effects=stack_effects,
    )


@pytest.mark.parametrize("kind", sorted(THUNK_EVENTS))
def test_thunk_lifecycle_events_match(initial_state, kind):
    transition = make_transition(
        initial_state,
        semantic_events=(SemanticEvent(kind),),
    )

    assert matching_capture_categories(
        transition,
        frozenset({"thunks"}),
    ) == frozenset({"thunks"})


@pytest.mark.parametrize("kind", sorted(REDUCTION_EVENTS))
def test_semantic_reduction_events_match(initial_state, kind):
    transition = make_transition(
        initial_state,
        semantic_events=(SemanticEvent(kind),),
    )

    assert matching_capture_categories(
        transition,
        frozenset({"reductions"}),
    ) == frozenset({"reductions"})


@pytest.mark.parametrize(
    "kind",
    [
        SemanticEventKind.FUNCTION_APPLIED,
        SemanticEventKind.VARIABLE_LOOKED_UP,
    ],
)
def test_non_reduction_events_do_not_match_reductions(
    initial_state,
    kind,
):
    transition = make_transition(
        initial_state,
        semantic_events=(SemanticEvent(kind),),
    )

    assert not matching_capture_categories(
        transition,
        frozenset({"reductions"}),
    )


@pytest.mark.parametrize(
    ("before", "after"),
    [
        (
            ExecutionPhase.EVALUATION,
            ExecutionPhase.RESULT_MATERIALIZATION,
        ),
        (
            ExecutionPhase.RESULT_MATERIALIZATION,
            ExecutionPhase.RESULT_MATERIALIZATION,
        ),
        (
            ExecutionPhase.RESULT_MATERIALIZATION,
            ExecutionPhase.EVALUATION,
        ),
    ],
)
def test_materialization_matches_phase_boundaries(
    initial_state,
    before,
    after,
):
    transition = make_transition(
        initial_state,
        phase_before=before,
        phase_after=after,
    )

    assert matching_capture_categories(
        transition,
        frozenset({"materialization"}),
    ) == frozenset({"materialization"})


def test_result_mode_selection_is_not_materialization(
    initial_state,
):
    transition = make_transition(
        initial_state,
        rule_id=RuleId.RESULT_SELECT_MODE,
    )

    assert not matching_capture_categories(
        transition,
        frozenset({"materialization"}),
    )


@pytest.mark.parametrize(
    "effect",
    [
        HeapAllocated(
            object_id=ObjectId(1),
            allocated_slots=1,
            object_type="ThunkPayload",
        ),
        HeapReplaced(
            object_id=ObjectId(1),
            previous_object_type="PendingThunk",
            new_object_type="Indirection",
        ),
    ],
)
def test_heap_changes_match(initial_state, effect):
    transition = make_transition(
        initial_state,
        heap_effects=(effect,),
    )

    assert matching_capture_categories(
        transition,
        frozenset({"heap"}),
    ) == frozenset({"heap"})


def test_heap_baseline_is_not_a_heap_change(initial_state):
    transition = make_transition(
        initial_state,
        heap_effects=(HeapBaselineRecorded(slots=0),),
    )

    assert not matching_capture_categories(
        transition,
        frozenset({"heap"}),
    )


@pytest.mark.parametrize(
    "effect",
    [
        StackPushed(frame_type="UpdateFrame"),
        StackPopped(frame_type="UpdateFrame"),
    ],
)
def test_stack_operations_match(initial_state, effect):
    transition = make_transition(
        initial_state,
        stack_effects=(effect,),
    )

    assert matching_capture_categories(
        transition,
        frozenset({"stack"}),
    ) == frozenset({"stack"})


def test_transition_can_match_multiple_categories(initial_state):
    transition = make_transition(
        initial_state,
        semantic_events=(
            SemanticEvent(SemanticEventKind.THUNK_UPDATED),
            SemanticEvent(SemanticEventKind.PRIMITIVE_REDUCED),
        ),
        heap_effects=(
            HeapReplaced(
                object_id=ObjectId(1),
                previous_object_type="EvaluatingThunk",
                new_object_type="Indirection",
            ),
        ),
    )

    selected = frozenset({
        "thunks",
        "heap",
        "reductions",
        "stack",
    })

    assert matching_capture_categories(
        transition,
        selected,
    ) == frozenset({
        "thunks",
        "heap",
        "reductions",
    })


def test_empty_selection_does_not_match(initial_state):
    transition = make_transition(
        initial_state,
        semantic_events=(
            SemanticEvent(SemanticEventKind.THUNK_CREATED),
        ),
    )

    assert matching_capture_categories(
        transition,
        frozenset(),
    ) == frozenset()


def test_rule_id_alone_does_not_imply_thunk_event(initial_state):
    transition = make_transition(
        initial_state,
        rule_id=RuleId.CORE_THUNK_UPDATE_WHNF,
    )

    assert not matching_capture_categories(
        transition,
        frozenset({"thunks"}),
    )


def test_unknown_capture_category_is_rejected():
    with pytest.raises(
        ValueError,
        match="Unsupported capture categories",
    ):
        validate_capture_categories(
            frozenset({"thunks", "unknown"})
        )


def test_session_factory_rejects_unknown_category():
    config = ExecutionConfig(
        machine_kind=MachineKind.CORE,
        strategy=Strategy.CBNEED,
        result_policy=ResultPolicy.WHNF_ONLY,
        execution_step_limit=100,
        result_node_limit=100,
        trace_mode=TraceMode.EVENTS,
    )

    with pytest.raises(
        ValueError,
        match="Unsupported capture categories",
    ):
        create_interactive_session(
            "main = 42",
            config,
            capture_categories=frozenset({"unknown"}),
        )


def test_supported_catalog_is_explicit():
    assert SUPPORTED_CAPTURE_CATEGORIES == frozenset({
        "thunks",
        "materialization",
        "heap",
        "stack",
        "reductions",
    })
