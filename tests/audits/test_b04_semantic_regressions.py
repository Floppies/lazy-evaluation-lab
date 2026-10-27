"""Focused operational properties exercised during the formal B04 audit."""

from lazy_lab.engine.core_machine import create_initial_core_state, run_batch
from lazy_lab.pipeline import compile_source
from lazy_lab.runtime.closures import Closure
from lazy_lab.runtime.control import Return
from lazy_lab.runtime.heap import Indirection
from lazy_lab.runtime.references import ImmediateInteger
from lazy_lab.runtime.state import (
    ExecutionConfig,
    MachineKind,
    ResultPolicy,
    Strategy,
    TraceMode,
)
from lazy_lab.runtime.transitions import BatchStopReason


def test_mutual_local_calls_preserve_captures_anchors_and_shadowing():
    program = compile_source(
        "bias = 100\n"
        "main = let { "
        "bias = 7; "
        "even n = if n == 0 then bias else odd (n - 1); "
        "odd n = if n == 0 then 0 else even (n - 1); "
        "alias = even "
        r"} in (\bias -> alias 4) 99"
    )
    config = ExecutionConfig(
        machine_kind=MachineKind.CORE,
        strategy=Strategy.CBV,
        result_policy=ResultPolicy.WHNF_ONLY,
        execution_step_limit=500,
        result_node_limit=100,
        trace_mode=TraceMode.FULL,
    )
    initial = create_initial_core_state(
        program, config, session_id="b04-mutual-captures"
    )

    result = run_batch(initial, config, max_steps=500)
    machine = result.state.machine_state

    assert result.stop_reason is BatchStopReason.WHNF_PENDING
    assert machine.control == Return(ImmediateInteger(7))
    assert machine.stack.depth == 0
    assert machine.local_environment is machine.global_environment

    closures = [
        cell.value
        for cell in machine.heap.cells.values()
        if isinstance(cell.value, Closure)
    ]
    even_closure = next(
        closure for closure in closures
        if set(closure.captured_locals.bindings) == {"bias", "odd"}
    )
    odd_anchor = even_closure.captured_locals.lookup("odd")
    odd_indirection = machine.heap.get(odd_anchor).value
    assert isinstance(odd_indirection, Indirection)
    odd_closure = machine.heap.get(odd_indirection.target).value
    assert isinstance(odd_closure, Closure)
    assert set(odd_closure.captured_locals.bindings) == {"even"}

    even_anchor = odd_closure.captured_locals.lookup("even")
    even_indirection = machine.heap.get(even_anchor).value
    assert isinstance(even_indirection, Indirection)
    assert machine.heap.get(even_indirection.target).value is even_closure

    caller = next(
        closure for closure in closures
        if set(closure.captured_locals.bindings) == {"alias"}
    )
    alias_anchor = caller.captured_locals.lookup("alias")
    alias_indirection = machine.heap.get(alias_anchor).value
    assert isinstance(alias_indirection, Indirection)
    assert alias_indirection.target is even_indirection.target

    # A mutual call must retain definition-site bias, not caller bias.
    bias_anchor = even_closure.captured_locals.lookup("bias")
    bias_indirection = machine.heap.get(bias_anchor).value
    assert bias_indirection == Indirection(ImmediateInteger(7))
    assert machine.heap.get(even_anchor).allocated_slots == 1
    assert machine.heap.get(odd_anchor).allocated_slots == 1
    assert initial.machine_state.heap.current_slots == 0
