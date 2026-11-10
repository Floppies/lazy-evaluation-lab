from dataclasses import replace
from typing import get_type_hints

import pytest

from lazy_lab.engine.core_machine import create_initial_core_state, run_batch
from lazy_lab.engine.result_consumer import (
    InvalidResultObservationError,
    advance_constructor_materialization,
    complete_constructor_materialization,
    finish_limited_materialization,
    request_materialization_field,
    select_result_mode,
    start_constructor_materialization,
)
from lazy_lab.pipeline import compile_source
from lazy_lab.runtime.control import Force, Return
from lazy_lab.runtime.materialization import start_materialization
from lazy_lab.runtime.observation import (
    CanonicalConstructor,
    CanonicalInteger,
    CanonicalPartialConstructor,
    CanonicalPending,
    PartialCanonicalValue,
)
from lazy_lab.runtime.references import ImmediateInteger
from lazy_lab.runtime.stack import MaterializationDemandFrame
from lazy_lab.runtime.state import (
    ExecutionConfig,
    ExecutionPhase,
    ExecutionState,
    ExecutionStatus,
    MachineKind,
    ResultPolicy,
    Strategy,
    TraceMode,
)
from lazy_lab.runtime.transitions import (
    BatchStopReason,
    RuleId,
    TransitionKind,
    TransitionResult,
)


def evaluated_constructor(
    *,
    strategy: Strategy = Strategy.CBV,
    policy: ResultPolicy = ResultPolicy.MATERIALIZE_COMPLETE_VALUE,
    node_limit: int = 100,
) -> tuple[ExecutionState, ExecutionConfig]:
    config = ExecutionConfig(
        machine_kind=MachineKind.CORE,
        strategy=strategy,
        result_policy=policy,
        execution_step_limit=200,
        result_node_limit=node_limit,
        trace_mode=TraceMode.FULL,
    )
    initial = create_initial_core_state(
        compile_source("main = (1 + 2) : []"),
        config,
        session_id="constructor-consumer",
    )
    evaluated = run_batch(initial, config, max_steps=200)
    assert evaluated.stop_reason is BatchStopReason.WHNF_PENDING
    return evaluated.state, config


def assert_administrative_transition(
    previous: ExecutionState,
    transition: TransitionResult,
    rule_id: RuleId,
) -> None:
    next_state = transition.next_state
    before = previous.machine_state
    after = next_state.machine_state
    assert transition.previous_state_id == previous.state_id
    assert next_state.state_id == previous.state_id + 1
    assert next_state.transition_index == previous.transition_index + 1
    assert transition.rule_id is rule_id
    assert transition.transition_kind is TransitionKind.RESULT_CONSUMER
    assert transition.phase_before is before.phase
    assert transition.phase_after is ExecutionPhase.RESULT_MATERIALIZATION
    assert after.phase is ExecutionPhase.RESULT_MATERIALIZATION
    assert after.evaluator_transition_count == before.evaluator_transition_count
    assert after.control == before.control
    assert after.local_environment is before.local_environment
    assert after.global_environment is before.global_environment
    assert after.heap is not before.heap
    assert dict(after.heap.cells) == dict(before.heap.cells)
    assert after.heap.current_slots == before.heap.current_slots
    assert after.heap.next_object_id == before.heap.next_object_id
    assert after.stack is not before.stack
    assert after.stack.frames == before.stack.frames


@pytest.mark.parametrize("strategy", [Strategy.CBV, Strategy.CBNEED])
@pytest.mark.parametrize(
    "policy",
    [ResultPolicy.MATERIALIZE_COMPLETE_VALUE, ResultPolicy.ASK_AT_WHNF],
)
def test_start_records_root_without_visiting_it(strategy, policy):
    state, config = evaluated_constructor(strategy=strategy, policy=policy)
    if policy is ResultPolicy.ASK_AT_WHNF:
        state = select_result_mode(
            state, config, ResultPolicy.MATERIALIZE_COMPLETE_VALUE,
        ).next_state

    transition = start_constructor_materialization(state, config)

    assert_administrative_transition(state, transition, RuleId.RESULT_MATERIALIZE_START)
    machine = transition.next_state.machine_state
    progress = machine.result_state.materialization
    assert progress is not None
    assert progress.root_reference == state.machine_state.control.reference
    assert progress.pending_reference == progress.root_reference
    assert progress.visited_nodes == 0
    assert progress.frames == ()
    assert not progress.awaiting_whnf
    assert machine.result_state.result_reference == progress.root_reference
    assert machine.result_state.resolved_result_mode is ResultPolicy.MATERIALIZE_COMPLETE_VALUE
    assert machine.status is ExecutionStatus.RUNNING
    assert transition.next_state.canonical_result is None
    assert state.machine_state.phase is ExecutionPhase.EVALUATION
    assert state.machine_state.result_state.materialization is None


@pytest.mark.parametrize(
    "invalid",
    [
        "status", "phase", "control", "stack", "non_constructor",
        "progress", "canonical_result", "whnf_policy", "unselected_ask",
        "selected_whnf", "wrong_selected_root", "previous_fixed_selection",
        "strategy", "machine_kind",
    ],
)
def test_start_rejects_invalid_inputs_without_mutating_them(invalid):
    state, config = evaluated_constructor()
    machine = state.machine_state
    root = machine.control.reference
    if invalid == "status":
        machine = replace(machine, status=ExecutionStatus.COMPLETED)
    elif invalid == "phase":
        machine = replace(machine, phase=ExecutionPhase.RESULT_MATERIALIZATION)
    elif invalid == "control":
        machine = replace(machine, control=Force(root))
    elif invalid == "stack":
        machine.stack.push(MaterializationDemandFrame(root, machine.local_environment))
    elif invalid == "non_constructor":
        machine = replace(machine, control=Return(ImmediateInteger(3)))
    elif invalid == "progress":
        machine = replace(machine, result_state=replace(
            machine.result_state, materialization=start_materialization(root),
        ))
    elif invalid == "canonical_result":
        state = replace(state, canonical_result=CanonicalPending())
    elif invalid == "whnf_policy":
        config = replace(config, result_policy=ResultPolicy.WHNF_ONLY)
    elif invalid == "unselected_ask":
        config = replace(config, result_policy=ResultPolicy.ASK_AT_WHNF)
    elif invalid in ("selected_whnf", "wrong_selected_root"):
        config = replace(config, result_policy=ResultPolicy.ASK_AT_WHNF)
        machine = replace(machine, result_state=replace(
            machine.result_state,
            resolved_result_mode=(
                ResultPolicy.WHNF_ONLY if invalid == "selected_whnf"
                else ResultPolicy.MATERIALIZE_COMPLETE_VALUE
            ),
            result_reference=(root if invalid == "selected_whnf" else ImmediateInteger(3)),
        ))
    elif invalid == "previous_fixed_selection":
        machine = replace(machine, result_state=replace(
            machine.result_state, result_reference=root,
        ))
    elif invalid == "strategy":
        config = replace(config, strategy=Strategy.CBNEED)
    elif invalid == "machine_kind":
        config = replace(config, machine_kind=MachineKind.STG, strategy=Strategy.CBNEED)
    state = replace(state, machine_state=machine)
    snapshot = state.snapshot()

    with pytest.raises(InvalidResultObservationError):
        start_constructor_materialization(state, config)

    assert state.machine_state.result_state == snapshot.machine_state.result_state
    assert dict(machine.heap.cells) == dict(snapshot.machine_state.heap.cells)
    assert machine.stack.frames == snapshot.machine_state.stack.frames
    assert machine.control == snapshot.machine_state.control


def test_advance_pauses_on_lazy_head_without_forcing_it():
    state, config = evaluated_constructor(strategy=Strategy.CBNEED)
    started = start_constructor_materialization(state, config).next_state
    root_progress = started.machine_state.result_state.materialization

    visited = advance_constructor_materialization(started, config)
    assert_administrative_transition(started, visited, RuleId.RESULT_MATERIALIZE_ADVANCE)
    progress = visited.next_state.machine_state.result_state.materialization
    assert progress.visited_nodes == 1
    assert not progress.awaiting_whnf
    assert root_progress.visited_nodes == 0

    paused = advance_constructor_materialization(visited.next_state, config)
    assert_administrative_transition(visited.next_state, paused, RuleId.RESULT_MATERIALIZE_ADVANCE)
    paused_progress = paused.next_state.machine_state.result_state.materialization
    assert paused_progress.awaiting_whnf
    assert paused_progress.pending_reference == progress.pending_reference
    assert paused_progress.visited_nodes == 1
    assert paused.next_state.machine_state.stack.depth == 0
    assert not progress.awaiting_whnf
    with pytest.raises(InvalidResultObservationError):
        advance_constructor_materialization(paused.next_state, config)


@pytest.mark.parametrize(
    "policy",
    [ResultPolicy.MATERIALIZE_COMPLETE_VALUE, ResultPolicy.ASK_AT_WHNF],
)
@pytest.mark.parametrize("node_limit", [3, 100])
def test_complete_publishes_existing_tree_even_with_exhausted_evaluator_budget(policy, node_limit):
    state, config = evaluated_constructor(policy=policy, node_limit=node_limit)
    if policy is ResultPolicy.ASK_AT_WHNF:
        state = select_result_mode(
            state, config, ResultPolicy.MATERIALIZE_COMPLETE_VALUE,
        ).next_state
    config = replace(config, execution_step_limit=state.machine_state.evaluator_transition_count)
    current = start_constructor_materialization(state, config).next_state
    for _ in range(3):
        transition = advance_constructor_materialization(current, config)
        assert_administrative_transition(current, transition, RuleId.RESULT_MATERIALIZE_ADVANCE)
        current = transition.next_state
    progress = current.machine_state.result_state.materialization
    assert progress.completed_value == CanonicalConstructor(
        "Cons", (CanonicalInteger(3), CanonicalConstructor("Nil", ())),
    )
    assert progress.visited_nodes == 3
    assert current.canonical_result is None

    transition = complete_constructor_materialization(current, config)

    assert_administrative_transition(current, transition, RuleId.RESULT_MATERIALIZE_COMPLETE)
    completed = transition.next_state
    assert completed.canonical_result is progress.completed_value
    assert completed.machine_state.result_state.materialization is progress
    assert completed.machine_state.status is ExecutionStatus.COMPLETED
    assert current.machine_state.status is ExecutionStatus.RUNNING
    with pytest.raises(InvalidResultObservationError):
        complete_constructor_materialization(completed, config)


@pytest.mark.parametrize("node_limit", [1, 2])
def test_result_limit_publishes_saved_partial_tree(node_limit):
    state, config = evaluated_constructor(node_limit=node_limit)
    current = start_constructor_materialization(state, config).next_state
    for _ in range(node_limit + 1):
        current = advance_constructor_materialization(current, config).next_state
    progress = current.machine_state.result_state.materialization
    assert progress.limit_reached
    assert progress.visited_nodes == node_limit
    assert progress.completed_value is None

    transition = finish_limited_materialization(current, config)

    assert_administrative_transition(current, transition, RuleId.RESULT_MATERIALIZE_RESULT_LIMIT)
    limited = transition.next_state
    assert limited.machine_state.status is ExecutionStatus.RESULT_LIMIT_REACHED
    assert limited.machine_state.result_state.materialization is progress
    assert limited.canonical_result is progress.partial_value
    assert limited.canonical_result == CanonicalPartialConstructor(
        "Cons",
        ((CanonicalInteger(3),) if node_limit == 2 else ()) + (CanonicalPending(),),
        unvisited_fields=1 if node_limit == 1 else 0,
    )
    assert current.canonical_result is None
    assert current.machine_state.status is ExecutionStatus.RUNNING
    with pytest.raises(InvalidResultObservationError):
        finish_limited_materialization(limited, config)


@pytest.mark.parametrize("during_forcing", [False, True])
def test_step_limit_preserves_progress_and_runtime_during_pending_demand(during_forcing):
    state, config = evaluated_constructor(strategy=Strategy.CBNEED)
    current = start_constructor_materialization(state, config).next_state
    for _ in range(2):
        current = advance_constructor_materialization(current, config).next_state
    if during_forcing:
        requested = request_materialization_field(current, config).next_state
        config = replace(config, execution_step_limit=(
            requested.machine_state.evaluator_transition_count + 1
        ))
        paused = run_batch(requested, config, max_steps=200)
        assert paused.stop_reason is BatchStopReason.EVALUATOR_BUDGET
        current = paused.state
        assert current.machine_state.stack.depth > 0
    else:
        config = replace(config, execution_step_limit=current.machine_state.evaluator_transition_count)
    progress = current.machine_state.result_state.materialization

    transition = finish_limited_materialization(current, config)

    assert_administrative_transition(current, transition, RuleId.RESULT_MATERIALIZE_EXECUTION_LIMIT)
    limited = transition.next_state
    assert limited.machine_state.status is ExecutionStatus.STEP_LIMIT_REACHED
    assert limited.machine_state.result_state.materialization is progress
    assert limited.canonical_result == CanonicalPartialConstructor(
        "Cons", (CanonicalPending(),), unvisited_fields=1,
    )
    assert progress.awaiting_whnf
    assert progress.partial_value is None
    assert not progress.limit_reached
    assert current.machine_state.status is ExecutionStatus.RUNNING
    assert current.canonical_result is None


def test_finish_rejects_exhausted_budget_without_pending_evaluation():
    state, config = evaluated_constructor()
    config = replace(config, execution_step_limit=state.machine_state.evaluator_transition_count)
    current = start_constructor_materialization(state, config).next_state
    with pytest.raises(InvalidResultObservationError):
        finish_limited_materialization(current, config)


def test_finish_rejects_pending_demand_with_remaining_evaluator_budget():
    state, config = evaluated_constructor(strategy=Strategy.CBNEED)
    current = start_constructor_materialization(state, config).next_state
    for _ in range(2):
        current = advance_constructor_materialization(current, config).next_state
    with pytest.raises(InvalidResultObservationError):
        finish_limited_materialization(current, config)


def test_lazy_constructor_completes_through_explicit_field_demands():
    state, config = evaluated_constructor(strategy=Strategy.CBNEED)
    original_cells = dict(state.machine_state.heap.cells)
    original_count = state.machine_state.evaluator_transition_count
    current = start_constructor_materialization(state, config).next_state
    demands = 0

    for _ in range(10):
        progress = current.machine_state.result_state.materialization
        if progress.completed_value is not None:
            break
        if progress.awaiting_whnf:
            requested = request_materialization_field(current, config)
            forced = run_batch(requested.next_state, config, max_steps=200)
            assert forced.stop_reason is BatchStopReason.WHNF_PENDING
            current = forced.state
            demands += 1
        else:
            current = advance_constructor_materialization(current, config).next_state
    else:
        raise AssertionError("Constructor materialization did not finish")

    completed = complete_constructor_materialization(current, config).next_state

    assert demands == 2
    assert completed.canonical_result == CanonicalConstructor(
        "Cons", (CanonicalInteger(3), CanonicalConstructor("Nil", ())),
    )
    assert completed.machine_state.evaluator_transition_count > original_count
    assert completed.machine_state.control == state.machine_state.control
    assert completed.machine_state.stack.depth == 0
    assert completed.machine_state.phase is ExecutionPhase.RESULT_MATERIALIZATION
    assert completed.machine_state.status is ExecutionStatus.COMPLETED
    assert dict(state.machine_state.heap.cells) == original_cells
    assert state.machine_state.stack.depth == 0
    assert state.machine_state.result_state.materialization is None


@pytest.mark.parametrize(
    "consumer",
    [advance_constructor_materialization, complete_constructor_materialization, finish_limited_materialization],
)
def test_consumers_require_active_progress(consumer):
    state, config = evaluated_constructor()
    with pytest.raises(InvalidResultObservationError):
        consumer(state, config)


def test_complete_rejects_incomplete_progress():
    state, config = evaluated_constructor()
    current = start_constructor_materialization(state, config).next_state
    with pytest.raises(InvalidResultObservationError):
        complete_constructor_materialization(current, config)


def test_canonical_result_annotation_accepts_partial_values():
    assert get_type_hints(ExecutionState)["canonical_result"] == PartialCanonicalValue | None
