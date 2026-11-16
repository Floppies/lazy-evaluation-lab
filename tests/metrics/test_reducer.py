
from dataclasses import replace

import pytest

from lazy_lab.core.nodes import CoreInt
from lazy_lab.metrics.events import (
    EventOrigin,
    OriginKind,
    SemanticEvent,
    SemanticEventKind,
)
from lazy_lab.metrics.reducer import reduce_metrics
from lazy_lab.metrics.state import InstrumentationState
from lazy_lab.runtime.control import EvaluateCore
from lazy_lab.runtime.environment import Environment
from lazy_lab.runtime.heap import Heap
from lazy_lab.runtime.stack import Stack
from lazy_lab.runtime.state import (
    ExecutionPhase,
    ExecutionState,
    ExecutionStatus,
    MachineKind,
    MachineState,
    Strategy,
)
from lazy_lab.runtime.transitions import (
    RuleId,
    TransitionKind,
    TransitionResult,
)
from lazy_lab.metrics.effects import (
    HeapAllocated,
    HeapReplaced,
    HeapBaselineRecorded,
    StackPushed,
    StackPopped,
)
from lazy_lab.runtime.references import ObjectId



def make_transition(
    *events: SemanticEvent,
    kind: TransitionKind = TransitionKind.EVALUATOR,
    phase_before: ExecutionPhase = ExecutionPhase.EVALUATION,
    phase_after: ExecutionPhase | None = None,
) -> TransitionResult:
    environment = Environment()

    machine = MachineState(
        machine_kind=MachineKind.CORE,
        strategy=Strategy.CBV,
        status=ExecutionStatus.RUNNING,
        phase=phase_after or phase_before,
        control=EvaluateCore(CoreInt(0)),
        local_environment=environment,
        global_environment=environment,
        heap=Heap(),
        stack=Stack(),
    )

    next_state = ExecutionState(
        state_id=1,
        session_id="metrics-test",
        transition_index=1,
        machine_state=machine,
    )

    return TransitionResult(
        previous_state_id=0,
        next_state=next_state,
        rule_id=RuleId.CORE_EVAL_INTEGER,
        transition_kind=kind,
        phase_before=phase_before,
        phase_after=phase_after or phase_before,
        semantic_events=events,
    )


def test_application_and_beta_count_as_one_reduction():
    origin = EventOrigin(kind=OriginKind.GENERATED)

    transition = make_transition(
        SemanticEvent(
            SemanticEventKind.FUNCTION_APPLIED,
            origin=origin,
        ),
        SemanticEvent(
            SemanticEventKind.BETA_REDUCED,
            origin=origin,
        ),
    )

    initial = InstrumentationState()
    updated = reduce_metrics(initial, transition)

    assert updated.counters.function_applications == 1
    assert updated.counters.beta_reductions == 1
    assert updated.counters.semantic_reductions == 1

    assert updated.counters.evaluator_transitions == 1
    assert initial.counters.semantic_reductions == 0


def test_curried_application_counts_each_unary_beta():
    transition = make_transition(
        SemanticEvent(SemanticEventKind.FUNCTION_APPLIED),
        SemanticEvent(SemanticEventKind.BETA_REDUCED),
    )

    once = reduce_metrics(InstrumentationState(), transition)
    twice = reduce_metrics(once, transition)

    assert twice.counters.function_applications == 2
    assert twice.counters.beta_reductions == 2
    assert twice.counters.semantic_reductions == 2


def test_transition_accounting_uses_phase_before():
    initial = InstrumentationState()

    entering_materialization = make_transition(
        phase_before=ExecutionPhase.EVALUATION,
        phase_after=ExecutionPhase.RESULT_MATERIALIZATION,
    )

    materialization_demand = make_transition(
        phase_before=ExecutionPhase.RESULT_MATERIALIZATION,
    )

    consumer = make_transition(
        kind=TransitionKind.RESULT_CONSUMER,
        phase_before=ExecutionPhase.RESULT_MATERIALIZATION,
    )

    state = reduce_metrics(initial, entering_materialization)
    state = reduce_metrics(state, materialization_demand)
    state = reduce_metrics(state, consumer)

    assert state.counters.evaluator_transitions == 2
    assert state.counters.result_demand_evaluator_transitions == 1
    assert state.counters.result_consumer_transitions == 1
    assert state.counters.semantic_reductions == 0


def test_heap_effects_count_allocations_and_baseline():
    first = replace(
        make_transition(),
        heap_effects=(
            HeapAllocated(
                object_id=ObjectId(0),
                allocated_slots=1,
                object_type="Reserved",
            ),
            HeapAllocated(
                object_id=ObjectId(1),
                allocated_slots=3,
                object_type="ThunkPayload",
            ),
            HeapReplaced(
                object_id=ObjectId(0),
                previous_object_type="Reserved",
                new_object_type="PendingThunk",
            ),
            HeapBaselineRecorded(slots=4),
        ),
    )

    state = reduce_metrics(InstrumentationState(), first)

    assert state.counters.total_allocations == 2
    assert state.counters.current_heap_slots == 4
    assert state.counters.peak_heap_slots == 4
    assert state.baseline_slots == 4
    assert state.additional_peak_over_baseline == 0

    second = replace(
        make_transition(),
        heap_effects=(
            HeapAllocated(
                object_id=ObjectId(2),
                allocated_slots=2,
                object_type="ConstructorValue",
            ),
        ),
    )

    updated = reduce_metrics(state, second)

    assert updated.counters.total_allocations == 3
    assert updated.counters.current_heap_slots == 6
    assert updated.counters.peak_heap_slots == 6
    assert updated.additional_peak_over_baseline == 2

    # Previous snapshots remain unchanged.
    assert state.counters.current_heap_slots == 4


def test_stack_peak_preserves_intermediate_depth():
    transition = replace(
        make_transition(),
        stack_effects=(
            StackPushed("ApplyFunctionFrame"),
            StackPushed("UpdateFrame"),
            StackPopped("UpdateFrame"),
            StackPopped("ApplyFunctionFrame"),
        ),
    )

    state = reduce_metrics(
        InstrumentationState(),
        transition,
    )

    assert state.counters.pushes == 2
    assert state.counters.pops == 2
    assert state.counters.current_frames == 0

    # Peak cannot be recovered from final depth alone.
    assert state.counters.peak_frames == 2


def test_cbneed_events_update_independent_counters():
    anchor = ObjectId(10)

    created = make_transition(
        SemanticEvent(
            SemanticEventKind.THUNK_CREATED,
            object_id=anchor,
        ),
    )

    forced = make_transition(
        SemanticEvent(
            SemanticEventKind.THUNK_DEMANDED,
            object_id=anchor,
        ),
        SemanticEvent(
            SemanticEventKind.THUNK_FORCE_STARTED,
            object_id=anchor,
        ),
    )

    updated = make_transition(
        SemanticEvent(
            SemanticEventKind.THUNK_UPDATED,
            object_id=anchor,
        ),
    )

    reused = make_transition(
        SemanticEvent(
            SemanticEventKind.THUNK_DEMANDED,
            object_id=anchor,
        ),
        SemanticEvent(
            SemanticEventKind.SHARED_RESULT_HIT,
            object_id=anchor,
        ),
    )

    state = InstrumentationState()

    for transition in (
        created,
        forced,
        updated,
        reused,
    ):
        state = reduce_metrics(state, transition)

    counters = state.counters

    assert counters.thunks_created == 1
    assert counters.thunk_demands == 2
    assert counters.thunks_forced == 1
    assert counters.thunks_updated == 1
    assert counters.shared_result_hits == 1
    assert counters.blackholes == 0
    assert counters.thunks_never_forced == 0

    assert counters.semantic_reductions == 0
    assert counters.total_allocations == 0


def test_blackhole_does_not_count_as_successful_update():
    anchor = ObjectId(20)

    transition = make_transition(
        SemanticEvent(
            SemanticEventKind.THUNK_CREATED,
            object_id=anchor,
        ),
        SemanticEvent(
            SemanticEventKind.THUNK_DEMANDED,
            object_id=anchor,
        ),
        SemanticEvent(
            SemanticEventKind.THUNK_FORCE_STARTED,
            object_id=anchor,
        ),
        SemanticEvent(
            SemanticEventKind.THUNK_DEMANDED,
            object_id=anchor,
        ),
        SemanticEvent(
            SemanticEventKind.BLACKHOLE_DETECTED,
            object_id=anchor,
        ),
    )

    updated = reduce_metrics(
        InstrumentationState(),
        transition,
    )

    assert updated.counters.thunk_demands == 2
    assert updated.counters.thunks_forced == 1
    assert updated.counters.thunks_updated == 0
    assert updated.counters.blackholes == 1
    assert updated.counters.shared_result_hits == 0


def test_baseline_must_match_accounted_heap():
    initial = InstrumentationState()

    allocated = replace(
        make_transition(),
        heap_effects=(
            HeapAllocated(
                object_id=ObjectId(0),
                allocated_slots=3,
                object_type="Reserved",
            ),
        ),
    )

    state = reduce_metrics(initial, allocated)

    wrong_baseline = replace(
        make_transition(),
        heap_effects=(HeapBaselineRecorded(slots=2),),
    )

    with pytest.raises(ValueError, match="does not match"):
        reduce_metrics(state, wrong_baseline)

    assert state.baseline_slots is None
    assert state.counters.current_heap_slots == 3

    correct_baseline = replace(
        make_transition(),
        heap_effects=(HeapBaselineRecorded(slots=3),),
    )

    updated = reduce_metrics(state, correct_baseline)

    assert updated.baseline_slots == 3

    with pytest.raises(ValueError, match="already recorded"):
        reduce_metrics(updated, correct_baseline)


def test_reducer_is_compositional_across_batches():
    transitions = (
        replace(
            make_transition(
                SemanticEvent(
                    SemanticEventKind.BETA_REDUCED
                )
            ),
            heap_effects=(
                HeapAllocated(
                    object_id=ObjectId(0),
                    allocated_slots=2,
                    object_type="Closure",
                ),
            ),
        ),
        replace(
            make_transition(),
            stack_effects=(
                StackPushed("ApplyFunctionFrame"),
            ),
        ),
        replace(
            make_transition(),
            stack_effects=(
                StackPopped("ApplyFunctionFrame"),
            ),
        ),
    )

    initial = InstrumentationState()

    sequential = initial
    for transition in transitions:
        sequential = reduce_metrics(
            sequential,
            transition,
        )

    first_batch = initial
    for transition in transitions[:2]:
        first_batch = reduce_metrics(
            first_batch,
            transition,
        )

    batched = first_batch
    for transition in transitions[2:]:
        batched = reduce_metrics(
            batched,
            transition,
        )

    assert sequential == batched
    assert initial.counters.evaluator_transitions == 0
    assert first_batch.counters.evaluator_transitions == 2

    assert sequential.counters.evaluator_transitions == 3
    assert sequential.counters.semantic_reductions == 1
    assert sequential.counters.current_heap_slots == 2
    assert sequential.counters.peak_frames == 1
    assert sequential.counters.current_frames == 0


def test_stack_underflow_preserves_previous_state():
    initial = InstrumentationState()

    transition = replace(
        make_transition(),
        stack_effects=(
            StackPopped("UpdateFrame"),
        ),
    )

    with pytest.raises(ValueError, match="underflow"):
        reduce_metrics(initial, transition)

    assert initial.counters.pushes == 0
    assert initial.counters.pops == 0
    assert initial.counters.current_frames == 0


def test_thunk_chain_depth_tracks_nested_update_frames():
    transition = replace(
        make_transition(),
        stack_effects=(
            StackPushed("UpdateFrame"),
            StackPushed("ApplyFunctionFrame"),
            StackPushed("UpdateFrame"),
            StackPopped("UpdateFrame"),
            StackPopped("ApplyFunctionFrame"),
            StackPopped("UpdateFrame"),
        ),
    )

    initial = InstrumentationState()
    result = reduce_metrics(initial, transition)

    counters = result.counters

    assert counters.pushes == 3
    assert counters.pops == 3
    assert counters.current_frames == 0
    assert counters.peak_frames == 3

    assert counters.current_thunk_chain_length == 0
    assert counters.max_thunk_chain_length == 2

    assert initial.counters.max_thunk_chain_length == 0


def test_thunk_chain_underflow_is_rejected():
    transition = replace(
        make_transition(),
        stack_effects=(
            StackPushed("ApplyFunctionFrame"),
            StackPopped("UpdateFrame"),
        ),
    )

    initial = InstrumentationState()

    with pytest.raises(
        ValueError,
        match="Thunk chain accounting underflow",
    ):
        reduce_metrics(initial, transition)

    assert initial == InstrumentationState()
