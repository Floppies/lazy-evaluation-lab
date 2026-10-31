
"""Integration tests for Call-by-Need closure application."""

import pytest

from lazy_lab.pipeline import compile_source
from lazy_lab.engine.core_machine import (
    create_initial_core_state,
    run_batch,
    step,
    UnsupportedTransitionError,
)
from lazy_lab.runtime.control import Return, Force
from lazy_lab.runtime.heap import Indirection
from lazy_lab.runtime.references import (
    HeapReference,
    ImmediateInteger,
)
from lazy_lab.runtime.stack import (
    ApplyFunctionFrame,
    RestoreEnvironmentFrame,
)
from lazy_lab.runtime.state import (
    ExecutionConfig,
    MachineKind,
    ResultPolicy,
    Strategy,
    TraceMode,
)
from lazy_lab.runtime.thunks import PendingThunk, ThunkPayload
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

    assert isinstance(machine.stack.peek(), ApplyFunctionFrame)
    assert machine.stack.peek().awaiting_whnf

    # The function has not yet been entered.
    assert isinstance(
        machine.heap.get(function_ref).value,
        PendingThunk,
    )

    previous_id = current.state_id
    previous_slots = machine.heap.current_slots

    # Temporary B05.4 boundary: not a non-function error.
    with pytest.raises(
        UnsupportedTransitionError,
        match="PendingThunk",
    ):
        step(current, config)

    # Rejected transitions do not mutate the input state.
    assert current.state_id == previous_id
    assert machine.heap.current_slots == previous_slots
    assert isinstance(
        machine.heap.get(function_ref).value,
        PendingThunk,
    )


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
