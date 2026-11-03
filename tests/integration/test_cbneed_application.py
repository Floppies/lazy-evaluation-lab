
"""Integration tests for Call-by-Need closure application."""

import pytest
from dataclasses import replace

from lazy_lab.pipeline import compile_source
from lazy_lab.engine.core_machine import (
    create_initial_core_state,
    run_batch,
    step,
    UnsupportedTransitionError,
    InvalidMachineStateError,
)
from lazy_lab.runtime.control import (
    Return,
    Force,
    EvaluateCore,
)
from lazy_lab.runtime.heap import Indirection
from lazy_lab.runtime.references import (
    HeapReference,
    ImmediateInteger,
)
from lazy_lab.runtime.stack import (
    ApplyFunctionFrame,
    RestoreEnvironmentFrame,
    UpdateFrame,
)
from lazy_lab.runtime.state import (
    ExecutionConfig,
    MachineKind,
    ResultPolicy,
    Strategy,
    TraceMode,
)
from lazy_lab.runtime.thunks import (
    PendingThunk,
    ThunkPayload,
    EvaluatingThunk,
)
from lazy_lab.runtime.transitions import BatchStopReason, RuleId
from lazy_lab.runtime.closures import Closure
from lazy_lab.core.nodes import (
    CoreApp,
    CoreBool,
    CoreInt,
    CorePrimOp,
)


def make_cbneed_config():
    return ExecutionConfig(
        machine_kind=MachineKind.CORE,
        strategy=Strategy.CBNEED,
        result_policy=ResultPolicy.WHNF_ONLY,
        execution_step_limit=150,
        result_node_limit=100,
        trace_mode=TraceMode.FULL,
    )


def advance_to_next_cbneed_body(state, config):
    """Advance through the next CBNeed closure-body entry.

    Return the state before the transition and its successor.
    """
    current = state

    for _ in range(100):
        transition = step(current, config)

        if transition.rule_id is RuleId.CORE_CBNEED_ENTER_BODY:
            return current, transition.next_state

        current = transition.next_state

    raise AssertionError("No CBNeed closure-body entry found")


def test_unused_argument_is_not_evaluated():
    program = compile_source(
        r"main = (\x -> 42) (1 + True)"
    )

    config = make_cbneed_config()
    initial = create_initial_core_state(
        program,
        config,
        session_id="cbneed-unused-argument",
    )

    result = run_batch(
        initial,
        config,
        max_steps=100,
    )

    assert result.stop_reason is BatchStopReason.WHNF_PENDING
    assert result.state.machine_state.control == Return(
        ImmediateInteger(42)
    )

    rule_ids = [entry.rule_id for entry in result.trace]

    assert RuleId.CORE_CBNEED_ENTER_BODY in rule_ids
    assert RuleId.CORE_CBV_EVAL_ARGUMENT not in rule_ids
    assert RuleId.CORE_CBV_REQUIRE_ARGUMENT_WHNF not in rule_ids

    # No primitive expression was evaluated.
    assert RuleId.CORE_EVAL_PRIMITIVE_START not in rule_ids
    assert RuleId.CORE_PRIM_EXECUTE not in rule_ids

    assert result.state.machine_state.stack.depth == 0


def test_cbneed_enters_body_with_pending_argument_thunk():
    program = compile_source(
        r"main = (\x -> 42) (20 + 1)"
    )

    config = make_cbneed_config()
    current = create_initial_core_state(
        program,
        config,
        session_id="cbneed-thunk-binding",
    )

    for _ in range(60):
        transition = step(current, config)

        if transition.rule_id is RuleId.CORE_CBNEED_ENTER_BODY:
            break

        current = transition.next_state
    else:
        raise AssertionError("CBNeed never entered the closure body")

    previous = current
    successor = transition.next_state

    before = previous.machine_state
    after = successor.machine_state

    assert isinstance(before.stack.peek(), ApplyFunctionFrame)
    assert isinstance(
        after.stack.peek(),
        RestoreEnvironmentFrame,
    )

    argument_ref = after.local_environment.lookup("x")
    assert isinstance(argument_ref, HeapReference)

    anchor = after.heap.get(argument_ref).value
    assert isinstance(anchor, PendingThunk)

    payload_cell = after.heap.get(anchor.payload_reference)
    assert isinstance(payload_cell.value, ThunkPayload)
    assert payload_cell.value.required_slots == 1

    # One payload slot and one stable anchor slot.
    assert after.heap.current_slots == before.heap.current_slots + 2

    # The function body has not demanded x.
    assert isinstance(
        after.heap.get(argument_ref).value,
        PendingThunk,
    )

    # The transition did not mutate the previous state.
    assert previous.machine_state.heap is not after.heap
    assert previous.machine_state.stack is not after.stack


def test_lazy_argument_captures_local_but_not_global_names():
    program = compile_source(
        "global_value = 100\n"
        r"main = (\x -> (\y -> 42) (x + global_value)) 20"
    )
    config = make_cbneed_config()

    initial = create_initial_core_state(
        program,
        config,
        session_id="cbneed-local-global-captures",
    )

    # First application: bind x to a thunk for 20.
    _, outer_state = advance_to_next_cbneed_body(
        initial, config
    )

    outer_x = outer_state.machine_state.local_environment.lookup(
        "x"
    )
    assert isinstance(outer_x, HeapReference)

    # Second application: defer x + global_value.
    _, inner_state = advance_to_next_cbneed_body(
        outer_state, config
    )

    machine = inner_state.machine_state
    y_ref = machine.local_environment.lookup("y")

    assert isinstance(y_ref, HeapReference)

    y_anchor = machine.heap.get(y_ref).value
    assert isinstance(y_anchor, PendingThunk)

    payload = machine.heap.get(
        y_anchor.payload_reference
    ).value
    assert isinstance(payload, ThunkPayload)

    assert set(payload.captured_locals.bindings) == {"x"}
    assert payload.captured_locals.lookup("x") is outer_x
    assert payload.required_slots == 2

    # Both deferred computations remain pending.
    assert isinstance(
        machine.heap.get(outer_x).value,
        PendingThunk,
    )

    # Completing the program must not demand either thunk.
    result = run_batch(inner_state, config, max_steps=100)

    assert result.stop_reason is BatchStopReason.WHNF_PENDING
    assert result.state.machine_state.control == Return(
        ImmediateInteger(42)
    )
    assert (
        result.state.machine_state.local_environment
        is result.state.machine_state.global_environment
    )


def test_lazy_argument_preserves_call_site_under_shadowing():
    program = compile_source(
        r"main = (\x -> (\x -> 42) (x + 1)) 10"
    )
    config = make_cbneed_config()

    initial = create_initial_core_state(
        program,
        config,
        session_id="cbneed-shadowed-parameter",
    )

    _, outer_state = advance_to_next_cbneed_body(
        initial, config
    )

    outer_x = outer_state.machine_state.local_environment.lookup(
        "x"
    )

    _, inner_state = advance_to_next_cbneed_body(
        outer_state, config
    )

    machine = inner_state.machine_state

    # The second lambda introduces another x binding.
    inner_x = machine.local_environment.lookup("x")

    assert isinstance(inner_x, HeapReference)
    assert isinstance(outer_x, HeapReference)
    assert inner_x != outer_x

    inner_anchor = machine.heap.get(inner_x).value
    assert isinstance(inner_anchor, PendingThunk)

    inner_payload = machine.heap.get(
        inner_anchor.payload_reference
    ).value
    assert isinstance(inner_payload, ThunkPayload)

    # The RHS x + 1 refers to the OUTER x.
    assert set(inner_payload.captured_locals.bindings) == {
        "x"
    }
    assert inner_payload.captured_locals.lookup("x") is outer_x

    # Neither thunk has been demanded.
    assert isinstance(
        machine.heap.get(outer_x).value,
        PendingThunk,
    )

    result = run_batch(inner_state, config, max_steps=100)

    assert result.stop_reason is BatchStopReason.WHNF_PENDING
    assert result.state.machine_state.control == Return(
        ImmediateInteger(42)
    )


def test_nested_lazy_argument_captures_two_thunk_references():
    program = compile_source(
        r"main = (\x -> (\z -> (\y -> 42) (x + z)) 30) 20"
    )
    config = make_cbneed_config()

    initial = create_initial_core_state(
        program,
        config,
        session_id="cbneed-nested-thunk-captures",
    )

    _, x_state = advance_to_next_cbneed_body(
        initial, config
    )

    x_ref = x_state.machine_state.local_environment.lookup("x")

    _, z_state = advance_to_next_cbneed_body(
        x_state, config
    )

    z_environment = z_state.machine_state.local_environment
    z_ref = z_environment.lookup("z")

    # The nested closure still refers to the original x.
    assert z_environment.lookup("x") is x_ref

    _, y_state = advance_to_next_cbneed_body(
        z_state, config
    )

    machine = y_state.machine_state
    y_ref = machine.local_environment.lookup("y")

    anchor = machine.heap.get(y_ref).value
    assert isinstance(anchor, PendingThunk)

    payload_cell = machine.heap.get(
        anchor.payload_reference
    )
    payload = payload_cell.value

    assert isinstance(payload, ThunkPayload)
    assert set(payload.captured_locals.bindings) == {
        "x", "z"
    }

    assert payload.captured_locals.lookup("x") is x_ref
    assert payload.captured_locals.lookup("z") is z_ref

    assert payload.required_slots == 3
    assert payload_cell.allocated_slots == 3
    assert machine.heap.get(y_ref).allocated_slots == 1

    assert isinstance(machine.heap.get(x_ref).value, PendingThunk)
    assert isinstance(machine.heap.get(z_ref).value, PendingThunk)

    result = run_batch(y_state, config, max_steps=100)

    assert result.stop_reason is BatchStopReason.WHNF_PENDING
    assert result.state.machine_state.control == Return(
        ImmediateInteger(42)
    )


def test_nested_lazy_argument_captures_two_thunk_references():
    program = compile_source(
        r"main = (\x -> (\z -> (\y -> 42) (x + z)) 30) 20"
    )
    config = make_cbneed_config()

    initial = create_initial_core_state(
        program,
        config,
        session_id="cbneed-nested-thunk-captures",
    )

    _, x_state = advance_to_next_cbneed_body(
        initial, config
    )

    x_ref = x_state.machine_state.local_environment.lookup("x")

    _, z_state = advance_to_next_cbneed_body(
        x_state, config
    )

    z_environment = z_state.machine_state.local_environment
    z_ref = z_environment.lookup("z")

    # The nested closure still refers to the original x.
    assert z_environment.lookup("x") is x_ref

    _, y_state = advance_to_next_cbneed_body(
        z_state, config
    )

    machine = y_state.machine_state
    y_ref = machine.local_environment.lookup("y")

    anchor = machine.heap.get(y_ref).value
    assert isinstance(anchor, PendingThunk)

    payload_cell = machine.heap.get(
        anchor.payload_reference
    )
    payload = payload_cell.value

    assert isinstance(payload, ThunkPayload)
    assert set(payload.captured_locals.bindings) == {
        "x", "z"
    }

    assert payload.captured_locals.lookup("x") is x_ref
    assert payload.captured_locals.lookup("z") is z_ref

    assert payload.required_slots == 3
    assert payload_cell.allocated_slots == 3
    assert machine.heap.get(y_ref).allocated_slots == 1

    assert isinstance(machine.heap.get(x_ref).value, PendingThunk)
    assert isinstance(machine.heap.get(z_ref).value, PendingThunk)

    result = run_batch(y_state, config, max_steps=100)

    assert result.stop_reason is BatchStopReason.WHNF_PENDING
    assert result.state.machine_state.control == Return(
        ImmediateInteger(42)
    )


def test_returned_closure_preserves_pending_thunk_capture():
    program = compile_source(
        r"main = (\x -> \y -> x) (1 + True)"
    )
    config = make_cbneed_config()

    initial = create_initial_core_state(
        program,
        config,
        session_id="cbneed-returned-closure",
    )

    result = run_batch(
        initial,
        config,
        max_steps=100,
    )

    assert result.stop_reason is BatchStopReason.WHNF_PENDING

    machine = result.state.machine_state
    assert isinstance(machine.control, Return)

    closure_ref = machine.control.reference
    assert isinstance(closure_ref, HeapReference)

    closure = machine.heap.get(closure_ref).value
    assert isinstance(closure, Closure)

    # The returned closure captures the original thunk.
    assert set(closure.captured_locals.bindings) == {"x"}

    x_ref = closure.captured_locals.lookup("x")
    assert isinstance(x_ref, HeapReference)

    x_anchor = machine.heap.get(x_ref).value
    assert isinstance(x_anchor, PendingThunk)

    # The caller's environment has been restored.
    assert machine.local_environment is machine.global_environment
    assert machine.stack.depth == 0

    # The invalid primitive argument was never evaluated.
    rules = [entry.rule_id for entry in result.trace]
    assert RuleId.CORE_EVAL_PRIMITIVE_START not in rules
    assert RuleId.CORE_PRIM_EXECUTE not in rules


def test_curried_application_preserves_original_capture():
    program = compile_source(
        r"main = (\x -> \y -> \z -> x) (1 + True) (2 + False)"
    )
    config = make_cbneed_config()

    initial = create_initial_core_state(
        program,
        config,
        session_id="cbneed-curried-returned-closure",
    )

    # First application binds x to a pending thunk.
    _, first_state = advance_to_next_cbneed_body(
        initial,
        config,
    )

    x_ref = first_state.machine_state.local_environment.lookup(
        "x"
    )

    # Second application binds y to another pending thunk.
    _, second_state = advance_to_next_cbneed_body(
        first_state,
        config,
    )

    y_ref = second_state.machine_state.local_environment.lookup(
        "y"
    )

    assert x_ref != y_ref

    # The second lambda still has access to the original x.
    assert (
        second_state.machine_state.local_environment.lookup("x")
        is x_ref
    )

    result = run_batch(
        second_state,
        config,
        max_steps=100,
    )

    assert result.stop_reason is BatchStopReason.WHNF_PENDING

    machine = result.state.machine_state
    assert isinstance(machine.control, Return)

    returned_ref = machine.control.reference
    assert isinstance(returned_ref, HeapReference)

    returned_closure = machine.heap.get(returned_ref).value
    assert isinstance(returned_closure, Closure)

    # The final \z -> x needs x but not y.
    assert set(returned_closure.captured_locals.bindings) == {
        "x"
    }
    assert returned_closure.captured_locals.lookup("x") is x_ref

    assert isinstance(machine.heap.get(x_ref).value, PendingThunk)
    assert isinstance(machine.heap.get(y_ref).value, PendingThunk)

    assert machine.stack.depth == 0
    assert machine.local_environment is machine.global_environment


def test_curried_application_does_not_force_unused_arguments():
    program = compile_source(
        r"main = (\x -> \y -> 42) (1 + True) (2 + False)"
    )
    config = make_cbneed_config()

    initial = create_initial_core_state(
        program,
        config,
        session_id="cbneed-curried-unused-arguments",
    )

    result = run_batch(
        initial,
        config,
        max_steps=100,
    )

    assert result.stop_reason is BatchStopReason.WHNF_PENDING
    assert result.state.machine_state.control == Return(
        ImmediateInteger(42)
    )

    rules = [entry.rule_id for entry in result.trace]

    assert rules.count(RuleId.CORE_CBNEED_ENTER_BODY) == 2
    assert RuleId.CORE_EVAL_PRIMITIVE_START not in rules
    assert RuleId.CORE_PRIM_EXECUTE not in rules

    machine = result.state.machine_state

    pending_thunks = [
        cell
        for cell in machine.heap.cells.values()
        if isinstance(cell.value, PendingThunk)
    ]

    assert len(pending_thunks) == 2
    assert machine.stack.depth == 0
    assert machine.local_environment is machine.global_environment


def test_cbneed_applies_function_through_global_alias():
    program = compile_source(
        "constant x = 42\n"
        "alias = constant\n"
        "main = alias (1 + True)"
    )
    config = make_cbneed_config()

    initial = create_initial_core_state(
        program,
        config,
        session_id="cbneed-global-function-alias",
    )

    result = run_batch(initial, config, max_steps=100)

    assert result.stop_reason is BatchStopReason.WHNF_PENDING
    assert result.state.machine_state.control == Return(
        ImmediateInteger(42)
    )

    rules = [entry.rule_id for entry in result.trace]

    assert RuleId.CORE_APPLY_REQUIRE_FUNCTION_WHNF in rules
    assert RuleId.CORE_FORCE_GLOBAL_RHS in rules
    assert RuleId.CORE_CBNEED_ENTER_BODY in rules

    # Only the function position was demanded.
    assert RuleId.CORE_EVAL_PRIMITIVE_START not in rules
    assert RuleId.CORE_PRIM_EXECUTE not in rules

    assert result.state.machine_state.stack.depth == 0


def test_cbneed_pending_function_position_requires_thunk_forcing():
    program = compile_source(
        r"main = (\f -> f (1 + True)) (\x -> 42)"
    )
    config = make_cbneed_config()

    current = create_initial_core_state(
        program,
        config,
        session_id="cbneed-pending-function-position",
    )

    for _ in range(100):
        machine = current.machine_state
        control = machine.control

        if (
            isinstance(control, Force)
            and isinstance(control.reference, HeapReference)
            and isinstance(
                machine.heap.get(control.reference).value,
                PendingThunk,
            )
        ):
            break

        current = step(current, config).next_state

    else:
        pytest.fail("No pending function thunk demand reached")

    machine = current.machine_state
    function_ref = machine.control.reference

    
    assert isinstance(
        machine.stack.peek(),
        ApplyFunctionFrame,
    )
    assert machine.stack.peek().awaiting_whnf

    pending = machine.heap.get(function_ref).value
    assert isinstance(pending, PendingThunk)

    payload = machine.heap.get(
        pending.payload_reference
    ).value
    assert isinstance(payload, ThunkPayload)

    previous_slots = machine.heap.current_slots
    previous_next_id = machine.heap.next_object_id
    previous_depth = machine.stack.depth

    transition = step(current, config)
    successor = transition.next_state
    next_machine = successor.machine_state

    assert transition.rule_id is RuleId.CORE_FORCE_THUNK_ENTER

    # The original anchor has entered EVALUATING.
    evaluating = next_machine.heap.get(function_ref).value

    assert isinstance(evaluating, EvaluatingThunk)
    assert evaluating.payload_reference == pending.payload_reference

    # No new allocation occurs during thunk entry.
    assert next_machine.heap.current_slots == previous_slots
    assert next_machine.heap.next_object_id == previous_next_id

    # The pending application remains below UpdateFrame.
    assert next_machine.stack.depth == previous_depth + 1

    frame = next_machine.stack.peek()
    assert isinstance(frame, UpdateFrame)

    assert frame.thunk_reference is function_ref
    assert frame.return_environment is machine.local_environment
    assert frame.awaiting_whnf is False

    # Execution resumes with the deferred Core expression.
    assert isinstance(next_machine.control, EvaluateCore)
    assert next_machine.control.expression is payload.expression

    # The previous ExecutionState remains unchanged.
    assert current.state_id + 1 == successor.state_id
    assert current.transition_index + 1 == successor.transition_index

    assert isinstance(
        machine.heap.get(function_ref).value,
        PendingThunk,
    )
    assert machine.stack.depth == previous_depth


def test_cbneed_non_callable_fails_before_argument_allocation():
    program = compile_source("")
    config = make_cbneed_config()

    expression = CoreApp(
        CoreInt(42),
        CorePrimOp(
            "+",
            (CoreInt(1), CoreBool(True)),
        ),
    )

    initial = create_initial_core_state(
        program,
        config,
        session_id="cbneed-invalid-function",
        entry=expression,
    )

    current = initial
    rules = []

    for _ in range(80):
        before_id = current.state_id
        before_slots = current.machine_state.heap.current_slots

        try:
            transition = step(current, config)

        except TypeError as exc:
            assert "Cannot apply a non-function value" in str(exc)

            # The failed transition did not mutate the input.
            assert current.state_id == before_id
            assert current.machine_state.heap.current_slots == (
                before_slots
            )
            break

        rules.append(transition.rule_id)
        current = transition.next_state

    else:
        pytest.fail("Invalid application was not rejected")

    heap_objects = [
        cell.value
        for cell in current.machine_state.heap.cells.values()
    ]

    assert not any(
        isinstance(value, (PendingThunk, ThunkPayload))
        for value in heap_objects
    )

    assert RuleId.CORE_EVAL_PRIMITIVE_START not in rules
    assert RuleId.CORE_CBNEED_ENTER_BODY not in rules

    assert initial.state_id == 0
    assert initial.machine_state.heap.current_slots == 0


def test_cbneed_complete_and_single_step_batches_are_equivalent():
    program = compile_source(
        r"main = (\x -> \y -> 42) (1 + True) (2 + False)"
    )
    config = make_cbneed_config()

    initial = create_initial_core_state(
        program,
        config,
        session_id="cbneed-batch-equivalence",
    )

    # Uninterrupted execution.
    full = run_batch(initial, config, max_steps=150)

    # Resume the same program one transition at a time.
    current = initial
    chunked_rules = []

    for _ in range(150):
        batch = run_batch(
            current,
            config,
            max_steps=1,
        )

        chunked_rules.extend(
            entry.rule_id for entry in batch.trace
        )
        current = batch.state

        if batch.stop_reason is BatchStopReason.WHNF_PENDING:
            break
    else:
        raise AssertionError("Chunked execution did not finish")

    assert full.stop_reason is BatchStopReason.WHNF_PENDING

    full_machine = full.state.machine_state
    chunked_machine = current.machine_state

    expected_result = Return(ImmediateInteger(42))

    assert full_machine.control == expected_result
    assert chunked_machine.control == expected_result

    full_rules = [
        entry.rule_id for entry in full.trace
    ]

    assert full_rules == chunked_rules

    assert full_rules.count(
        RuleId.CORE_CBNEED_ENTER_BODY
    ) == 2

    assert RuleId.CORE_EVAL_PRIMITIVE_START not in full_rules
    assert RuleId.CORE_CBV_EVAL_ARGUMENT not in full_rules

    assert (
        full_machine.evaluator_transition_count
        == chunked_machine.evaluator_transition_count
    )
    assert full.state.transition_index == current.transition_index

    assert (
        full_machine.heap.current_slots
        == chunked_machine.heap.current_slots
    )
    assert (
        full_machine.heap.next_object_id
        == chunked_machine.heap.next_object_id
    )

    # Compare structural allocation signatures.
    # ThunkPayload intentionally does not use structural equality.
    def heap_signature(machine):
        return tuple(
            (
                cell.object_id,
                type(cell.value).__name__,
                cell.allocated_slots,
            )
            for cell in machine.heap.cells.values()
        )

    assert heap_signature(full_machine) == heap_signature(
        chunked_machine
    )

    assert full_machine.stack.depth == 0
    assert chunked_machine.stack.depth == 0

    assert (
        full_machine.local_environment
        is full_machine.global_environment
    )
    assert (
        chunked_machine.local_environment
        is chunked_machine.global_environment
    )

    # Neither run may mutate the initial state.
    assert initial.state_id == 0
    assert initial.transition_index == 0
    assert initial.machine_state.heap.current_slots == 0


def test_cbneed_trace_modes_preserve_execution():
    program = compile_source(
        r"main = (\x -> \y -> 42) (1 + True) (2 + False)"
    )

    full_config = make_cbneed_config()
    metrics_config = replace(
        full_config,
        trace_mode=TraceMode.METRICS_ONLY,
    )

    initial = create_initial_core_state(
        program,
        full_config,
        session_id="cbneed-trace-mode-equivalence",
    )

    full = run_batch(
        initial,
        full_config,
        max_steps=150,
    )

    metrics = run_batch(
        initial,
        metrics_config,
        max_steps=150,
    )

    assert full.stop_reason == metrics.stop_reason
    assert full.stop_reason is BatchStopReason.WHNF_PENDING

    left = full.state.machine_state
    right = metrics.state.machine_state

    assert left.control == right.control
    assert left.control == Return(ImmediateInteger(42))

    assert (
        left.evaluator_transition_count
        == right.evaluator_transition_count
    )
    assert full.state.transition_index == metrics.state.transition_index

    assert left.heap.current_slots == right.heap.current_slots
    assert left.heap.next_object_id == right.heap.next_object_id

    assert left.stack.depth == right.stack.depth == 0

    # Trace retention must not affect machine execution.
    assert len(full.trace) > 0
    assert metrics.trace == ()


def test_thunk_entry_restores_captured_lexical_scope():
    program = compile_source(
        r"main = (\x -> (\f -> f (1 + True)) (\y -> x)) 30"
    )
    config = make_cbneed_config()

    current = create_initial_core_state(
        program,
        config,
        session_id="cbneed-thunk-entry-scope",
    )

    for _ in range(120):
        machine = current.machine_state
        control = machine.control

        if (
            isinstance(control, Force)
            and isinstance(control.reference, HeapReference)
            and isinstance(
                machine.heap.get(control.reference).value,
                PendingThunk,
            )
        ):
            break

        current = step(current, config).next_state

    else:
        pytest.fail("Pending function thunk demand not reached")

    machine = current.machine_state
    thunk_ref = machine.control.reference

    pending = machine.heap.get(thunk_ref).value
    payload = machine.heap.get(
        pending.payload_reference
    ).value

    assert isinstance(payload, ThunkPayload)
    assert set(payload.captured_locals.bindings) == {"x"}

    captured_x = payload.captured_locals.lookup("x")

    transition = step(current, config)
    next_machine = transition.next_state.machine_state

    assert transition.rule_id is RuleId.CORE_FORCE_THUNK_ENTER

    # The thunk uses its captures over the global environment.
    thunk_env = next_machine.local_environment

    assert thunk_env.parent is next_machine.global_environment
    assert set(thunk_env.bindings) == {"x"}
    assert thunk_env.lookup("x") is captured_x

    # The caller's local parameter f is not inherited.
    assert "f" not in thunk_env.bindings

    # The caller's complete environment is preserved instead.
    update_frame = next_machine.stack.peek()

    assert isinstance(update_frame, UpdateFrame)
    assert update_frame.return_environment is machine.local_environment

    assert isinstance(
        next_machine.heap.get(captured_x).value,
        PendingThunk,
    )

    # Entry does not force a captured dependency.
    assert next_machine.control.expression is payload.expression


def test_update_frame_demands_rhs_whnf_before_update():
    program = compile_source(
        r"main = (\f -> f (1 + True)) (\x -> 42)"
    )
    config = make_cbneed_config()

    current = create_initial_core_state(
        program,
        config,
        session_id="cbneed-update-whnf",
    )

    # Find the first RHS return handled by UpdateFrame.
    for _ in range(100):
        machine = current.machine_state

        if (
            isinstance(machine.control, Return)
            and machine.stack.depth > 0
            and isinstance(machine.stack.peek(), UpdateFrame)
            and not machine.stack.peek().awaiting_whnf
        ):
            break

        current = step(current, config).next_state

    else:
        pytest.fail("UpdateFrame RHS return was not reached")

    before = current.machine_state
    original_frame = before.stack.peek()
    result_ref = before.control.reference

    assert isinstance(result_ref, HeapReference)
    assert isinstance(
        before.heap.get(original_frame.thunk_reference).value,
        EvaluatingThunk,
    )

    # Stage 1: request explicit WHNF demand.
    transition = step(current, config)

    assert transition.rule_id is RuleId.CORE_THUNK_REQUIRE_WHNF

    awaiting_state = transition.next_state
    awaiting = awaiting_state.machine_state

    assert awaiting.control == Force(result_ref)
    assert awaiting.stack.depth == before.stack.depth

    awaiting_frame = awaiting.stack.peek()
    assert isinstance(awaiting_frame, UpdateFrame)
    assert awaiting_frame.awaiting_whnf is True
    assert original_frame.awaiting_whnf is False

    assert awaiting_frame.thunk_reference is (
        original_frame.thunk_reference
    )
    assert awaiting_frame.return_environment is (
        original_frame.return_environment
    )

    # Stage 2: forcing the closure returns its WHNF reference.
    forced = step(awaiting_state, config)

    assert forced.rule_id is RuleId.CORE_FORCE_FUNCTION_WHNF

    verified_state = forced.next_state
    verified = verified_state.machine_state

    assert verified.control == Return(result_ref)
    assert verified.stack.peek().awaiting_whnf is True

    # B05.5 boundary: WHNF is ready, update is not implemented.
    with pytest.raises(
        UnsupportedTransitionError,
        match="update pending B05.5",
    ):
        step(verified_state, config)

    # No premature update or environment restoration.
    assert isinstance(
        verified.heap.get(original_frame.thunk_reference).value,
        EvaluatingThunk,
    )
    assert verified.local_environment is (
        before.local_environment
    )
    assert verified.stack.depth == before.stack.depth

    # Historical states remain unchanged.
    assert original_frame.awaiting_whnf is False
    assert isinstance(
        before.heap.get(original_frame.thunk_reference).value,
        EvaluatingThunk,
    )


def test_update_frame_rejects_unresolved_second_stage_result():
    program = compile_source(
        r"main = (\f -> f 10) (\x -> 42)"
    )
    config = make_cbneed_config()

    current = create_initial_core_state(
        program,
        config,
        session_id="cbneed-invalid-update-return",
    )

    for _ in range(100):
        machine = current.machine_state

        if (
            isinstance(machine.control, Return)
            and machine.stack.depth > 0
            and isinstance(machine.stack.peek(), UpdateFrame)
            and not machine.stack.peek().awaiting_whnf
        ):
            break

        current = step(current, config).next_state

    else:
        pytest.fail("UpdateFrame return not reached")

    # Advance to the frame's WHNF-demand stage.
    awaiting_state = step(current, config).next_state

    assert isinstance(
        awaiting_state.machine_state.control, Force
    )
    assert awaiting_state.machine_state.stack.peek().awaiting_whnf

    # Construct an invalid continuation return:
    # the original EvaluatingThunk anchor is not WHNF.
    machine = awaiting_state.machine_state

    invalid_machine = replace(
        machine,
        control=Return(
            machine.stack.peek().thunk_reference
        ),
    )
    invalid_state = replace(
        awaiting_state,
        machine_state=invalid_machine,
    )

    with pytest.raises(
        InvalidMachineStateError,
        match="Thunk demand resumed without WHNF",
    ):
        step(invalid_state, config)

    # Failure must not mutate the supplied state.
    assert invalid_state.machine_state.control == Return(
        machine.stack.peek().thunk_reference
    )
    assert isinstance(
        invalid_state.machine_state.heap.get(
            machine.stack.peek().thunk_reference
        ).value,
        EvaluatingThunk,
    )
    assert invalid_state.machine_state.stack.peek().awaiting_whnf
