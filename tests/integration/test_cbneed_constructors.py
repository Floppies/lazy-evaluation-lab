from lazy_lab.pipeline import compile_source
from lazy_lab.engine.core_machine import (
    create_initial_core_state,
    step,
)
from lazy_lab.runtime.constructors import ConstructorValue
from lazy_lab.runtime.control import Return
from lazy_lab.runtime.references import HeapReference
from lazy_lab.runtime.thunks import PendingThunk
from lazy_lab.runtime.transitions import RuleId

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