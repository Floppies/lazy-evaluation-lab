from dataclasses import replace

from lazy_lab.engine.core_machine import (
    create_initial_core_state,
    run_batch,
)
from lazy_lab.engine.result_consumer import request_materialization_field
from lazy_lab.pipeline import compile_source
from lazy_lab.runtime.constructors import ConstructorValue
from lazy_lab.runtime.control import Force, Return
from lazy_lab.runtime.materialization import (
    advance_materialization,
    start_materialization,
)
from lazy_lab.runtime.references import ImmediateInteger
from lazy_lab.runtime.stack import MaterializationDemandFrame
from lazy_lab.runtime.state import (
    ExecutionConfig,
    ExecutionPhase,
    MachineKind,
    ResultPolicy,
    Strategy,
    TraceMode,
)
from lazy_lab.runtime.thunks import PendingThunk
from lazy_lab.runtime.transitions import (
    BatchStopReason,
    RuleId,
    TransitionKind,
)


def test_cbneed_materialization_field_demand_resumes_at_root_whnf():
    config = ExecutionConfig(
        machine_kind=MachineKind.CORE,
        strategy=Strategy.CBNEED,
        result_policy=ResultPolicy.MATERIALIZE_COMPLETE_VALUE,
        execution_step_limit=200,
        result_node_limit=100,
        trace_mode=TraceMode.FULL,
    )
    initial = create_initial_core_state(
        compile_source("main = (1 + 2) : []"),
        config,
        session_id="materialization-field-demand",
    )
    evaluated = run_batch(initial, config, max_steps=200)

    assert evaluated.stop_reason is BatchStopReason.WHNF_PENDING
    evaluated_machine = evaluated.state.machine_state
    assert isinstance(evaluated_machine.control, Return)
    root_reference = evaluated_machine.control.reference
    constructor = evaluated_machine.heap.get(root_reference).value
    assert isinstance(constructor, ConstructorValue)
    assert constructor.tag == "Cons"
    head_reference = constructor.fields[0]
    assert isinstance(
        evaluated_machine.heap.get(head_reference).value,
        PendingThunk,
    )

    progress = start_materialization(root_reference)
    progress = advance_materialization(evaluated_machine.heap, progress)
    paused_progress = advance_materialization(
        evaluated_machine.heap,
        progress,
    )
    assert paused_progress.awaiting_whnf is True
    assert paused_progress.pending_reference == head_reference

    # Prepare the bridge directly; automatic phase entry is separate work.
    prepared_machine = replace(
        evaluated.state.machine_state,
        phase=ExecutionPhase.RESULT_MATERIALIZATION,
        result_state=replace(
            evaluated.state.machine_state.result_state,
            materialization=paused_progress,
        ),
    )
    prepared_state = replace(
        evaluated.state,
        machine_state=prepared_machine,
    )
    original_cells = dict(prepared_machine.heap.cells)
    original_slots = prepared_machine.heap.current_slots
    original_next_object_id = prepared_machine.heap.next_object_id
    original_frames = prepared_machine.stack.frames
    original_count = prepared_machine.evaluator_transition_count

    requested = request_materialization_field(prepared_state, config)

    assert requested.transition_kind is TransitionKind.RESULT_CONSUMER
    requested_machine = requested.next_state.machine_state
    assert isinstance(requested_machine.control, Force)
    assert requested_machine.control.reference == head_reference
    assert isinstance(
        requested_machine.stack.peek(),
        MaterializationDemandFrame,
    )
    assert requested_machine.evaluator_transition_count == original_count

    result = run_batch(requested.next_state, config, max_steps=200)

    assert result.stop_reason is BatchStopReason.WHNF_PENDING
    machine = result.state.machine_state
    assert machine.stack.depth == 0
    materialization = machine.result_state.materialization
    assert materialization is not None
    assert materialization.awaiting_whnf is False
    assert materialization.pending_reference == ImmediateInteger(3)
    assert machine.control == Return(root_reference)
    assert machine.phase is ExecutionPhase.RESULT_MATERIALIZATION
    assert machine.evaluator_transition_count > original_count

    assert RuleId.CORE_MATERIALIZATION_FIELD_RESUME in (
        entry.rule_id for entry in result.trace
    )
    evaluator_entries = tuple(
        entry
        for entry in result.trace
        if entry.transition_kind is TransitionKind.EVALUATOR
    )
    assert evaluator_entries
    assert machine.evaluator_transition_count == (
        original_count + len(evaluator_entries)
    )
    for entry in evaluator_entries:
        assert entry.phase_before is ExecutionPhase.RESULT_MATERIALIZATION
        assert entry.phase_after is ExecutionPhase.RESULT_MATERIALIZATION

    # Forcing must leave the pre-request snapshot intact.
    before = prepared_state.machine_state
    assert dict(before.heap.cells) == original_cells
    assert before.heap.current_slots == original_slots
    assert before.heap.next_object_id == original_next_object_id
    assert before.stack.frames == original_frames == ()
    assert before.result_state.materialization is paused_progress
    assert paused_progress.awaiting_whnf is True
    assert paused_progress.pending_reference == head_reference
    assert before.control == Return(root_reference)
    assert before.evaluator_transition_count == original_count
