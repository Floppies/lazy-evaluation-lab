from lazy_lab.pipeline import compile_source
from lazy_lab.engine.core_machine import (
    create_initial_core_state,
    run_batch,
    step,
)
from lazy_lab.runtime.constructors import ConstructorValue
from lazy_lab.runtime.control import EvaluateCore, Return
from lazy_lab.runtime.references import ImmediateInteger
from lazy_lab.runtime.stack import ConstructorFieldsFrame
from lazy_lab.runtime.state import Strategy
from lazy_lab.runtime.transitions import BatchStopReason, RuleId

from tests.integration.test_core_runtime import make_config


def test_cbv_nil_is_allocated_immediately():
    config = make_config(strategy=Strategy.CBV)

    initial = create_initial_core_state(
        compile_source("main = []"),
        config,
        session_id="cbv-nil",
    )

    result = run_batch(initial, config, max_steps=100)

    assert result.stop_reason is BatchStopReason.WHNF_PENDING

    machine = result.state.machine_state
    value = machine.heap.get(machine.control.reference).value

    assert isinstance(value, ConstructorValue)
    assert value.tag == "Nil"
    assert value.fields == ()

    assert RuleId.CORE_CBV_ALLOCATE_CONSTRUCTOR in (
        entry.rule_id for entry in result.trace
    )


def test_cbv_cons_starts_with_first_field():
    config = make_config(strategy=Strategy.CBV)

    current = create_initial_core_state(
        compile_source("main = 1 : []"),
        config,
        session_id="cbv-cons-start",
    )

    for _ in range(30):
        transition = step(current, config)
        current = transition.next_state

        if (
            transition.rule_id
            is RuleId.CORE_CBV_EVAL_CONSTRUCTOR_START
        ):
            break
    else:
        raise AssertionError(
            "CBV constructor evaluation did not start"
        )

    machine = current.machine_state

    assert isinstance(machine.control, EvaluateCore)
    assert isinstance(machine.stack.peek(), ConstructorFieldsFrame)

    frame = machine.stack.peek()

    assert frame.constructor == "Cons"
    assert frame.evaluated_fields == ()
    assert len(frame.remaining_fields) == 1
    assert frame.awaiting_whnf is False


def test_cbv_cons_evaluates_fields_before_allocation():
    config = make_config(strategy=Strategy.CBV)

    initial = create_initial_core_state(
        compile_source("main = 1 : []"),
        config,
        session_id="cbv-cons-complete",
    )

    result = run_batch(initial, config, max_steps=100)

    assert result.stop_reason is BatchStopReason.WHNF_PENDING

    machine = result.state.machine_state

    assert isinstance(machine.control, Return)

    outer_cons = machine.heap.get(
        machine.control.reference
    ).value

    assert isinstance(outer_cons, ConstructorValue)
    assert outer_cons.tag == "Cons"

    head_ref, tail_ref = outer_cons.fields

    assert head_ref == ImmediateInteger(1)

    tail_value = machine.heap.get(tail_ref).value

    assert isinstance(tail_value, ConstructorValue)
    assert tail_value.tag == "Nil"
    assert tail_value.fields == ()

    rules = tuple(entry.rule_id for entry in result.trace)

    assert RuleId.CORE_CBV_REQUIRE_CONSTRUCTOR_FIELD_WHNF in rules
    assert RuleId.CORE_CBV_EVAL_NEXT_CONSTRUCTOR_FIELD in rules
    assert RuleId.CORE_CBV_ALLOCATE_CONSTRUCTOR in rules


def test_cbv_constructor_evaluates_head_expression():
    config = make_config(strategy=Strategy.CBV)

    initial = create_initial_core_state(
        compile_source("main = (1 + 2) : []"),
        config,
        session_id="cbv-cons-expression",
    )

    result = run_batch(initial, config, max_steps=100)

    assert result.stop_reason is BatchStopReason.WHNF_PENDING

    machine = result.state.machine_state

    constructor = machine.heap.get(
        machine.control.reference
    ).value

    assert isinstance(constructor, ConstructorValue)
    assert constructor.fields[0] == ImmediateInteger(3)