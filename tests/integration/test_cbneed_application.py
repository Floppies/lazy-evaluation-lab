
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

