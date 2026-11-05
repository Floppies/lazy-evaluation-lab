from lazy_lab.pipeline import compile_source
from .test_cbneed_application import make_cbneed_config
from lazy_lab.engine.core_machine import (
    create_initial_core_state,
    run_batch,
    step,
)
from lazy_lab.runtime.transitions import BatchStopReason, RuleId
from lazy_lab.runtime.control import Return
from lazy_lab.runtime.heap import Indirection
from lazy_lab.runtime.references import ImmediateInteger
from lazy_lab.runtime.thunks import (
    PendingThunk,
    ThunkPayload,
)

def test_cbneed_global_values_use_reserved_thunk_anchors():
    program = compile_source(
        "value = 20 + 1\nmain = value + value"
    )
    config = make_cbneed_config()

    initial = create_initial_core_state(
        program,
        config,
        session_id="cbneed-global-installation",
    )

    reserved = step(initial, config)

    assert reserved.rule_id is (
        RuleId.CORE_INIT_RESERVE_GLOBAL_SCOPE
    )

    current = reserved.next_state
    global_env = current.machine_state.global_environment

    original_refs = {
        binding.name: global_env.lookup(binding.name)
        for binding in program.bindings
    }

    # Install each global RHS without entering evaluation.
    for _ in program.bindings:
        transition = step(current, config)

        assert transition.rule_id is (
            RuleId.CORE_INIT_INSTALL_GLOBAL
        )
        current = transition.next_state

    machine = current.machine_state

    for binding in program.bindings:
        reference = original_refs[binding.name]
        cell = machine.heap.get(reference)

        assert cell.allocated_slots == 1
        assert isinstance(cell.value, PendingThunk)

        payload = machine.heap.get(
            cell.value.payload_reference
        ).value

        assert isinstance(payload, ThunkPayload)
        assert payload.expression is binding.rhs

        # Globals are resolved through global_environment.
        assert not payload.captured_locals.bindings
        assert payload.captured_locals.parent is None

    assert machine.stack.depth == 0

    # Initialization cannot mutate earlier snapshots.
    assert initial.machine_state.heap.current_slots == 0


def test_cbneed_global_binding_is_evaluated_once():
    program = compile_source(
        "value = 20 + 1\nmain = value + value"
    )
    config = make_cbneed_config()

    initial = create_initial_core_state(
        program,
        config,
        session_id="cbneed-global-sharing",
    )

    result = run_batch(
        initial,
        config,
        max_steps=150,
    )

    assert result.stop_reason is BatchStopReason.WHNF_PENDING

    machine = result.state.machine_state

    assert machine.control == Return(ImmediateInteger(42))
    assert machine.stack.depth == 0

    value_ref = machine.global_environment.lookup("value")
    main_ref = machine.global_environment.lookup("main")

    assert machine.heap.get(value_ref).value == Indirection(
        ImmediateInteger(21)
    )
    assert machine.heap.get(main_ref).value == Indirection(
        ImmediateInteger(42)
    )

    rules = [entry.rule_id for entry in result.trace]

    # One demand for main and one for value.
    assert rules.count(RuleId.CORE_FORCE_THUNK_ENTER) == 2
    assert rules.count(RuleId.CORE_THUNK_UPDATE_WHNF) == 2

    # The value RHS and main RHS each perform one addition.
    assert rules.count(RuleId.CORE_PRIM_EXECUTE) == 2

    # The second reference to value follows its update.
    assert rules.count(RuleId.CORE_FORCE_INDIRECTION) == 1

    assert RuleId.CORE_ROOT_REQUIRE_WHNF in rules

