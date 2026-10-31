
"""Integration tests for Call-by-Need closure application."""

from lazy_lab.pipeline import compile_source
from lazy_lab.engine.core_machine import (
    create_initial_core_state,
    run_batch,
    step,
)
from lazy_lab.runtime.control import Return
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
