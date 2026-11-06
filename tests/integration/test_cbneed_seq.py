from dataclasses import replace

import pytest

from lazy_lab.engine.core_machine import (
    create_initial_core_state,
    run_batch,
    step,
)
from lazy_lab.pipeline import compile_source
from lazy_lab.runtime.control import Return
from lazy_lab.runtime.heap import Indirection
from lazy_lab.runtime.predefined import PartialPredefinedFunction
from lazy_lab.runtime.references import ImmediateInteger
from lazy_lab.runtime.state import ExecutionStatus
from lazy_lab.runtime.thunks import PendingThunk
from lazy_lab.runtime.transitions import BatchStopReason, RuleId
from tests.integration.test_cbneed_application import make_cbneed_config, thunk_transition_anchors


def advance_to_seq_saturation(initial, config):
    """Return the state immediately after seq saturation."""
    current = initial
    rules = []

    for _ in range(config.execution_step_limit):
        transition = step(current, config)
        rules.append(transition.rule_id)

        if transition.rule_id is RuleId.CORE_SEQ_SATURATE:
            return transition.next_state, tuple(rules)

        current = transition.next_state

    raise AssertionError("seq saturation was not reached")


def test_cbneed_partial_seq_does_not_force_argument():
    program = compile_source(
        "loop = loop\n"
        "main = seq loop"
    )
    config = make_cbneed_config()

    initial = create_initial_core_state(
        program,
        config,
        session_id="cbneed-seq-partial-divergent",
    )

    result = run_batch(initial, config, max_steps=150)

    assert result.stop_reason is BatchStopReason.WHNF_PENDING

    machine = result.state.machine_state
    assert isinstance(machine.control, Return)

    partial_ref = machine.control.reference
    partial = machine.heap.get(partial_ref).value

    assert isinstance(partial, PartialPredefinedFunction)
    assert partial.name == "seq"
    assert partial.remaining_arity == 1

    argument_ref = partial.applied_arguments[0]
    assert isinstance(
        machine.heap.get(argument_ref).value,
        PendingThunk,
    )

    loop_ref = machine.global_environment.lookup("loop")
    assert isinstance(
        machine.heap.get(loop_ref).value,
        PendingThunk,
    )

    rules = [entry.rule_id for entry in result.trace]

    assert rules.count(RuleId.CORE_PREDEFINED_PARTIAL_APPLY) == 1
    assert RuleId.CORE_BLACKHOLE_DETECTED not in rules

def test_cbneed_partial_seq_defers_arithmetic():
    program = compile_source("main = seq (2 + 3)")
    config = make_cbneed_config()

    initial = create_initial_core_state(
        program,
        config,
        session_id="cbneed-seq-partial-arithmetic",
    )

    result = run_batch(initial, config, max_steps=150)

    assert result.stop_reason is BatchStopReason.WHNF_PENDING

    partial_ref = result.state.machine_state.control.reference
    partial = result.state.machine_state.heap.get(partial_ref).value

    assert isinstance(partial, PartialPredefinedFunction)

    argument_ref = partial.applied_arguments[0]
    assert isinstance(
        result.state.machine_state.heap.get(argument_ref).value,
        PendingThunk,
    )

    rules = [entry.rule_id for entry in result.trace]

    assert RuleId.CORE_PRIM_EXECUTE not in rules
    assert RuleId.CORE_PREDEFINED_PARTIAL_APPLY in rules

def test_cbneed_seq_forces_first_argument_before_saturation():
    program = compile_source(
        "main = seq (20 + 1) 42"
    )
    config = make_cbneed_config()

    initial = create_initial_core_state(
        program, config,
        session_id="cbneed-seq-saturation",
    )

    result = run_batch(initial, config, max_steps=150)

    assert result.stop_reason is BatchStopReason.WHNF_PENDING

    machine = result.state.machine_state
    assert machine.control == Return(ImmediateInteger(42))
    assert machine.stack.depth == 0

    rules = [entry.rule_id for entry in result.trace]

    assert (
        rules.index(RuleId.CORE_SEQ_REQUIRE_FIRST_WHNF)
        < rules.index(RuleId.CORE_PRIM_EXECUTE)
        < rules.index(RuleId.CORE_SEQ_SATURATE)
    )


def test_cbneed_seq_detects_blackhole_in_first_argument():
    program = compile_source(
        "main = seq (let { x = x } in x) 42"
    )
    config = make_cbneed_config()

    initial = create_initial_core_state(
        program, config,
        session_id="cbneed-seq-first-blackhole",
    )

    result = run_batch(initial, config, max_steps=150)

    assert result.stop_reason is BatchStopReason.TERMINAL_STATUS
    assert result.state.machine_state.status is (
        ExecutionStatus.BLACKHOLE_DETECTED
    )

    rules = [entry.rule_id for entry in result.trace]

    assert RuleId.CORE_SEQ_REQUIRE_FIRST_WHNF in rules
    assert RuleId.CORE_BLACKHOLE_DETECTED in rules
    assert RuleId.CORE_SEQ_SATURATE not in rules


def test_cbneed_seq_defers_second_argument_until_demanded():
    program = compile_source(
        "main = seq 10 (20 + 22)"
    )
    config = make_cbneed_config()

    initial = create_initial_core_state(
        program,
        config,
        session_id="cbneed-seq-deferred-second",
    )

    saturated, rules_before = advance_to_seq_saturation(
        initial, config
    )

    machine = saturated.machine_state

    assert isinstance(machine.control, Return)

    second_ref = machine.control.reference

    assert isinstance(
        machine.heap.get(second_ref).value,
        PendingThunk,
    )

    # The arithmetic in the second argument has not run.
    assert RuleId.CORE_PRIM_EXECUTE not in rules_before

    # A surrounding demand now forces the result.
    completed = run_batch(
        saturated, config, max_steps=150
    )

    assert completed.stop_reason is BatchStopReason.WHNF_PENDING
    assert completed.state.machine_state.control == Return(
        ImmediateInteger(42)
    )

    rules_after = [
        entry.rule_id for entry in completed.trace
    ]

    assert rules_after.count(RuleId.CORE_PRIM_EXECUTE) == 1

    assert completed.state.machine_state.heap.get(
        second_ref
    ).value == Indirection(ImmediateInteger(42))

    # The snapshot at saturation remains unchanged.
    assert isinstance(
        machine.heap.get(second_ref).value,
        PendingThunk,
    )


def test_cbneed_seq_second_blackhole_occurs_after_saturation():
    program = compile_source(
        "loop = loop\n"
        "main = seq 10 loop"
    )
    config = make_cbneed_config()

    initial = create_initial_core_state(
        program,
        config,
        session_id="cbneed-seq-second-blackhole",
    )

    saturated, rules_before = advance_to_seq_saturation(
        initial, config
    )

    machine = saturated.machine_state

    second_ref = machine.control.reference
    loop_ref = machine.global_environment.lookup("loop")

    assert isinstance(
        machine.heap.get(second_ref).value,
        PendingThunk,
    )
    assert isinstance(
        machine.heap.get(loop_ref).value,
        PendingThunk,
    )

    assert RuleId.CORE_BLACKHOLE_DETECTED not in rules_before

    completed = run_batch(
        saturated, config, max_steps=150
    )

    assert completed.stop_reason is BatchStopReason.TERMINAL_STATUS
    assert completed.state.machine_state.status is (
        ExecutionStatus.BLACKHOLE_DETECTED
    )

    rules_after = [
        entry.rule_id for entry in completed.trace
    ]

    assert RuleId.CORE_BLACKHOLE_DETECTED in rules_after
    assert RuleId.CORE_SEQ_SATURATE not in rules_after

    # Saturation snapshot still has a pending loop.
    assert isinstance(
        machine.heap.get(loop_ref).value,
        PendingThunk,
    )


def test_cbneed_seq_returns_an_applicable_function():
    program = compile_source(
        r"main = (seq 10 (\x -> x + 1)) 41"
    )
    config = make_cbneed_config()

    initial = create_initial_core_state(
        program,
        config,
        session_id="cbneed-seq-function-result",
    )

    saturated, _ = advance_to_seq_saturation(
        initial, config
    )

    second_ref = saturated.machine_state.control.reference

    assert isinstance(
        saturated.machine_state.heap.get(second_ref).value,
        PendingThunk,
    )

    result = run_batch(
        saturated, config, max_steps=150
    )

    assert result.stop_reason is BatchStopReason.WHNF_PENDING
    assert result.state.machine_state.control == Return(
        ImmediateInteger(42)
    )

    rules = [entry.rule_id for entry in result.trace]

    assert RuleId.CORE_FORCE_THUNK_ENTER in rules
    assert RuleId.CORE_CBNEED_ENTER_BODY in rules

    # The returned function is evaluated only when needed.
    assert isinstance(
        saturated.machine_state.heap.get(second_ref).value,
        PendingThunk,
    )


@pytest.mark.parametrize(
    "source, expected",
    [
        (
            "partial = seq 10\n"
            "main = partial 42",
            42,
        ),
        (
            "main = let { partial = seq 10; "
            "alias = partial } in alias 42",
            42,
        ),
        (
            r"main = (\f -> f 42) (seq 10)",
            42,
        ),
        (
            r"main = (\f -> f 10 42) seq",
            42,
        ),
    ],
)
def test_cbneed_seq_is_first_class(source, expected):
    program = compile_source(source)
    config = make_cbneed_config()

    initial = create_initial_core_state(
        program,
        config,
        session_id="cbneed-seq-first-class",
    )

    result = run_batch(initial, config, max_steps=150)
    machine = result.state.machine_state

    assert result.stop_reason is BatchStopReason.WHNF_PENDING
    assert machine.control == Return(
        ImmediateInteger(expected)
    )
    assert machine.stack.depth == 0

    rules = [entry.rule_id for entry in result.trace]

    assert RuleId.CORE_PREDEFINED_PARTIAL_APPLY in rules
    assert RuleId.CORE_SEQ_REQUIRE_FIRST_WHNF in rules
    assert RuleId.CORE_SEQ_SATURATE in rules


def test_cbneed_shared_partial_seq_memoizes_first_argument():
    program = compile_source(
        "partial = seq (20 + 1)\n"
        "main = partial 41 + partial 42"
    )
    config = replace(
        make_cbneed_config(),
        execution_step_limit=300,
    )

    initial = create_initial_core_state(
        program,
        config,
        session_id="cbneed-seq-shared-partial",
    )

    result = run_batch(initial, config, max_steps=300)

    assert result.stop_reason is BatchStopReason.WHNF_PENDING

    machine = result.state.machine_state
    assert machine.control == Return(ImmediateInteger(83))

    partial_global_ref = machine.global_environment.lookup(
        "partial"
    )

    # The global binding memoizes the partial function.
    global_value = machine.heap.get(partial_global_ref).value

    assert isinstance(global_value, Indirection)

    partial = machine.heap.get(global_value.target).value

    assert isinstance(partial, PartialPredefinedFunction)

    first_ref = partial.applied_arguments[0]

    # Both saturations share the same evaluated first argument.
    assert machine.heap.get(first_ref).value == Indirection(
        ImmediateInteger(21)
    )

    rules = [entry.rule_id for entry in result.trace]

    assert rules.count(RuleId.CORE_PREDEFINED_PARTIAL_APPLY) == 1
    assert rules.count(RuleId.CORE_SEQ_REQUIRE_FIRST_WHNF) == 2
    assert rules.count(RuleId.CORE_SEQ_SATURATE) == 2

    # First argument arithmetic once; final addition once.
    assert rules.count(RuleId.CORE_PRIM_EXECUTE) == 2

    anchors = thunk_transition_anchors(
        initial,
        config,
        result.trace,
    )

    assert anchors[RuleId.CORE_FORCE_THUNK_ENTER].count(
        first_ref
    ) == 1

    assert anchors[RuleId.CORE_THUNK_UPDATE_WHNF].count(
        first_ref
    ) == 1


@pytest.mark.parametrize(
    "source, expected",
    [
        (
            "seq x y = x + y\n"
            "main = seq 10 20",
            30,
        ),
        (
            "main = let { seq x y = x } "
            "in seq 10 20",
            10,
        ),
        (
            r"main = (\seq -> seq 10 20) "
            r"(\x -> \y -> y)",
            20,
        ),
    ],
)
def test_cbneed_user_defined_seq_shadows_predefined(
    source, expected
):
    program = compile_source(source)
    config = make_cbneed_config()

    initial = create_initial_core_state(
        program,
        config,
        session_id="cbneed-seq-shadowing",
    )

    result = run_batch(initial, config, max_steps=150)

    assert result.stop_reason is BatchStopReason.WHNF_PENDING
    assert result.state.machine_state.control == Return(
        ImmediateInteger(expected)
    )

    rules = [entry.rule_id for entry in result.trace]

    assert RuleId.CORE_CBNEED_ENTER_BODY in rules
    assert RuleId.CORE_PREDEFINED_PARTIAL_APPLY not in rules
    assert RuleId.CORE_SEQ_REQUIRE_FIRST_WHNF not in rules
    assert RuleId.CORE_SEQ_SATURATE not in rules


def test_cbneed_seq_batch_execution_is_deterministic():
    program = compile_source(
        "partial = seq (20 + 1)\n"
        "main = partial 42"
    )
    config = replace(
        make_cbneed_config(),
        execution_step_limit=300,
    )

    initial = create_initial_core_state(
        program,
        config,
        session_id="cbneed-seq-batching",
    )

    full = run_batch(initial, config, max_steps=300)

    current = initial
    collected_trace = []

    for _ in range(config.execution_step_limit):
        batch = run_batch(
            current,
            config,
            max_steps=1,
        )

        collected_trace.extend(batch.trace)
        current = batch.state

        if batch.stop_reason is BatchStopReason.WHNF_PENDING:
            break

        assert batch.stop_reason is BatchStopReason.BATCH_LIMIT
    else:
        pytest.fail("Chunked seq execution did not finish")

    assert full.stop_reason is BatchStopReason.WHNF_PENDING

    assert current.machine_state.control == Return(
        ImmediateInteger(42)
    )
    assert full.state.machine_state.control == (
        current.machine_state.control
    )

    assert tuple(collected_trace) == full.trace

    assert current.transition_index == full.state.transition_index
    assert (
        current.machine_state.evaluator_transition_count
        == full.state.machine_state.evaluator_transition_count
    )

    assert (
        current.machine_state.heap.current_slots
        == full.state.machine_state.heap.current_slots
    )

    assert (
        current.machine_state.heap.next_object_id
        == full.state.machine_state.heap.next_object_id
    )

    assert current.machine_state.stack.depth == 0
    assert full.state.machine_state.stack.depth == 0

    # Original execution state is unchanged.
    assert initial.transition_index == 0
    assert initial.machine_state.heap.current_slots == 0
