from dataclasses import replace

from lazy_lab.pipeline import compile_source
from lazy_lab.engine.core_machine import (
    create_initial_core_state,
    run_batch,
    step,
)
from lazy_lab.runtime.constructors import ConstructorValue
from lazy_lab.runtime.control import Force, Return
from lazy_lab.runtime.heap import Indirection
from lazy_lab.runtime.references import HeapReference
from lazy_lab.runtime.thunks import PendingThunk, ThunkPayload
from lazy_lab.runtime.transitions import BatchStopReason, RuleId

from tests.integration.test_cbneed_application import (
    make_cbneed_config,
)


def test_cbneed_constructor_allocates_deferred_fields():
    program = compile_source("main = 1 : []")
    config = make_cbneed_config()

    current = create_initial_core_state(
        program,
        config,
        session_id="cbneed-constructor",
    )

    for _ in range(30):
        transition = step(current, config)
        current = transition.next_state

        if (
            transition.rule_id
            is RuleId.CORE_CBNEED_EVAL_CONSTRUCTOR
        ):
            break
    else:
        raise AssertionError(
            "CBNeed constructor transition was not reached"
        )

    machine = current.machine_state

    assert isinstance(machine.control, Return)

    constructor_ref = machine.control.reference
    constructor = machine.heap.get(constructor_ref).value

    assert isinstance(constructor, ConstructorValue)
    assert constructor.tag == "Cons"
    assert len(constructor.fields) == 2

    for field_ref in constructor.fields:
        assert isinstance(field_ref, HeapReference)
        assert isinstance(
            machine.heap.get(field_ref).value,
            PendingThunk,
        )


def test_cbneed_constructor_reaches_whnf_without_forcing_fields():
    config = make_cbneed_config()

    program = compile_source(
        "loop = loop\n"
        "main = 1 : loop"
    )

    initial = create_initial_core_state(
        program,
        config,
        session_id="constructor-whnf",
    )

    result = run_batch(
        initial,
        config,
        max_steps=150,
    )

    assert result.stop_reason is BatchStopReason.WHNF_PENDING

    machine = result.state.machine_state
    assert isinstance(machine.control, Return)

    constructor_ref = machine.control.reference
    constructor = machine.heap.get(constructor_ref).value

    assert isinstance(constructor, ConstructorValue)
    assert constructor.tag == "Cons"

    for field_ref in constructor.fields:
        assert isinstance(
            machine.heap.get(field_ref).value,
            PendingThunk,
        )

    rule_ids = tuple(entry.rule_id for entry in result.trace)

    assert RuleId.CORE_FORCE_CONSTRUCTOR_WHNF in rule_ids
    assert RuleId.CORE_THUNK_UPDATE_WHNF in rule_ids


def test_constructor_field_captures_local_reference():
    program = compile_source(
        r"main = (\x -> x : []) (1 + 2)"
    )
    config = make_cbneed_config()

    initial = create_initial_core_state(
        program,
        config,
        session_id="constructor-local-capture",
    )

    result = run_batch(initial, config, max_steps=150)

    assert result.stop_reason is BatchStopReason.WHNF_PENDING

    machine = result.state.machine_state
    constructor_ref = machine.control.reference
    constructor = machine.heap.get(constructor_ref).value

    assert isinstance(constructor, ConstructorValue)
    assert constructor.tag == "Cons"

    head_ref, tail_ref = constructor.fields

    head_thunk = machine.heap.get(head_ref).value
    tail_thunk = machine.heap.get(tail_ref).value

    assert isinstance(head_thunk, PendingThunk)
    assert isinstance(tail_thunk, PendingThunk)

    head_payload = machine.heap.get(
        head_thunk.payload_reference
    ).value

    tail_payload = machine.heap.get(
        tail_thunk.payload_reference
    ).value

    assert isinstance(head_payload, ThunkPayload)
    assert isinstance(tail_payload, ThunkPayload)

    # Only the local free variable is captured.
    assert set(head_payload.captured_locals.bindings) == {"x"}

    captured_x = head_payload.captured_locals.lookup("x")

    # x still denotes the original, unevaluated argument.
    assert isinstance(
        machine.heap.get(captured_x).value,
        PendingThunk,
    )

    # The Nil expression has no local free variables.
    assert not tail_payload.captured_locals.bindings


def test_constructor_field_shares_global_result():
    program = compile_source(
        "xs = 2 : []\n"
        "main = 1 : xs"
    )
    config = replace(
        make_cbneed_config(),
        execution_step_limit=300,
    )

    initial = create_initial_core_state(
        program,
        config,
        session_id="constructor-global-sharing",
    )

    outer_result = run_batch(
        initial, config, max_steps=300
    )

    assert outer_result.stop_reason is BatchStopReason.WHNF_PENDING

    machine = outer_result.state.machine_state
    outer_ref = machine.control.reference
    outer_cons = machine.heap.get(outer_ref).value

    assert isinstance(outer_cons, ConstructorValue)

    tail_ref = outer_cons.fields[1]
    global_ref = machine.global_environment.lookup("xs")

    assert tail_ref != global_ref

    assert isinstance(
        machine.heap.get(tail_ref).value,
        PendingThunk,
    )
    assert isinstance(
        machine.heap.get(global_ref).value,
        PendingThunk,
    )

    # Simulate a consumer demanding the tail.
    demand_state = replace(
        outer_result.state,
        machine_state=replace(
            machine,
            control=Force(tail_ref),
        ),
    )

    demanded = run_batch(
        demand_state, config, max_steps=300
    )

    assert demanded.stop_reason is BatchStopReason.WHNF_PENDING

    updated_heap = demanded.state.machine_state.heap

    tail_value = updated_heap.get(tail_ref).value
    global_value = updated_heap.get(global_ref).value

    assert isinstance(tail_value, Indirection)
    assert isinstance(global_value, Indirection)

    # Both anchors share the same evaluated constructor.
    assert tail_value.target == global_value.target

    shared_cons = updated_heap.get(tail_value.target).value
    assert isinstance(shared_cons, ConstructorValue)