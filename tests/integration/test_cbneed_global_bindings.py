import pytest

from lazy_lab.metrics.events import SemanticEventKind
from lazy_lab.metrics.reducer import reduce_metrics
from lazy_lab.metrics.state import InstrumentationState
from lazy_lab.pipeline import compile_source
from .test_cbneed_application import (
    make_cbneed_config,
    thunk_transition_anchors,
)
from lazy_lab.engine.core_machine import (
    create_initial_core_state,
    run_batch,
    step,
)
from lazy_lab.runtime.transitions import BatchStopReason, RuleId, TraceEntry
from lazy_lab.runtime.control import Force, Return
from lazy_lab.runtime.heap import Indirection, Reserved
from lazy_lab.runtime.references import ImmediateInteger
from lazy_lab.runtime.thunks import (
    EvaluatingThunk,
    PendingThunk,
    ThunkPayload,
)
from lazy_lab.runtime.closures import Closure


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


def test_cbneed_forward_global_aliases_share_whnf():
    program = compile_source(
        "main = alias + base\n"
        "alias = base\n"
        "base = 20 + 1"
    )
    config = make_cbneed_config()

    initial = create_initial_core_state(
        program,
        config,
        session_id="cbneed-forward-global-aliases",
    )

    # Reserve the complete global scope.
    reserved = step(initial, config)

    assert reserved.rule_id is (
        RuleId.CORE_INIT_RESERVE_GLOBAL_SCOPE
    )

    reserved_machine = reserved.next_state.machine_state
    env = reserved_machine.global_environment

    main_ref = env.lookup("main")
    alias_ref = env.lookup("alias")
    base_ref = env.lookup("base")

    assert len({main_ref, alias_ref, base_ref}) == 3

    # All identities exist before any RHS is evaluated.
    for reference in (main_ref, alias_ref, base_ref):
        assert isinstance(
            reserved_machine.heap.get(reference).value,
            Reserved,
        )

    result = run_batch(
        reserved.next_state,
        config,
        max_steps=140,
    )

    assert result.stop_reason is BatchStopReason.WHNF_PENDING

    machine = result.state.machine_state

    assert machine.control == Return(ImmediateInteger(42))
    assert machine.stack.depth == 0

    # Stable global addresses are preserved.
    assert machine.global_environment.lookup("main") == main_ref
    assert machine.global_environment.lookup("alias") == alias_ref
    assert machine.global_environment.lookup("base") == base_ref

    assert machine.heap.get(base_ref).value == Indirection(
        ImmediateInteger(21)
    )
    assert machine.heap.get(alias_ref).value == Indirection(
        ImmediateInteger(21)
    )
    assert machine.heap.get(main_ref).value == Indirection(
        ImmediateInteger(42)
    )

    rules = [entry.rule_id for entry in result.trace]

    # main, alias and base are each entered and updated once.
    assert rules.count(RuleId.CORE_FORCE_THUNK_ENTER) == 3
    assert rules.count(RuleId.CORE_THUNK_UPDATE_WHNF) == 3

    # base RHS: 20 + 1
    # main RHS: 21 + 21
    assert rules.count(RuleId.CORE_PRIM_EXECUTE) == 2

    assert RuleId.CORE_FORCE_INDIRECTION in rules
    assert RuleId.CORE_FORCE_GLOBAL_RHS not in rules

    # The reserved snapshot retains its previous contents.
    assert isinstance(
        reserved_machine.heap.get(base_ref).value,
        Reserved,
    )


def test_cbneed_global_value_is_shared_across_function_calls():
    program = compile_source(
        "base = 20 + 1\n"
        "make n = base + n\n"
        "main = make 1 + make 2"
    )
    config = make_cbneed_config()

    initial = create_initial_core_state(
        program,
        config,
        session_id="cbneed-global-sharing-across-calls",
    )

    result = run_batch(
        initial,
        config,
        max_steps=150,
    )

    assert result.stop_reason is BatchStopReason.WHNF_PENDING

    machine = result.state.machine_state

    assert machine.control == Return(ImmediateInteger(45))
    assert machine.stack.depth == 0

    env = machine.global_environment

    base_ref = env.lookup("base")
    make_ref = env.lookup("make")
    main_ref = env.lookup("main")

    assert machine.heap.get(base_ref).value == Indirection(
        ImmediateInteger(21)
    )
    assert machine.heap.get(main_ref).value == Indirection(
        ImmediateInteger(45)
    )

    # A global lambda is installed directly as a closure.
    make_closure = machine.heap.get(make_ref).value

    assert isinstance(make_closure, Closure)
    assert not make_closure.captured_locals.bindings

    rules = [entry.rule_id for entry in result.trace]

    # Each call uses the same closure and creates its own argument thunk.
    current = initial
    argument_refs = []
    for entry in result.trace:
        transition = step(current, config)
        assert TraceEntry.from_transition(transition) == entry

        if entry.rule_id is RuleId.CORE_CBNEED_ENTER_BODY:
            assert current.machine_state.control == Return(make_ref)
            argument_refs.append(
                transition.next_state.machine_state.local_environment.lookup("n")
            )

        current = transition.next_state

    assert len(set(argument_refs)) == 2
    assert rules.count(RuleId.CORE_CBNEED_ENTER_BODY) == 2

    anchors = thunk_transition_anchors(initial, config, result.trace)
    first_argument_ref, second_argument_ref = argument_refs
    # main, base and both arguments are entered once; make is already WHNF.
    assert anchors[RuleId.CORE_FORCE_THUNK_ENTER] == [
        main_ref,
        base_ref,
        first_argument_ref,
        second_argument_ref,
    ]
    assert anchors[RuleId.CORE_THUNK_UPDATE_WHNF] == [
        base_ref,
        first_argument_ref,
        second_argument_ref,
        main_ref,
    ]
    assert make_ref not in anchors[RuleId.CORE_FORCE_THUNK_ENTER]

    # base is demanded twice but evaluated once.
    assert rules.count(RuleId.CORE_FORCE_INDIRECTION) == 1

    # 20+1, 21+1, 21+2, and the final addition.
    assert rules.count(RuleId.CORE_PRIM_EXECUTE) == 4

    assert RuleId.CORE_FORCE_GLOBAL_RHS not in rules


def test_cbneed_global_recursive_value_not_demanded_is_left_pending():
    program = compile_source(
        "unused = unused\n"
        "base = 21\n"
        "main = base"
    )
    config = make_cbneed_config()

    initial = create_initial_core_state(
        program,
        config,
        session_id="cbneed-unused-recursive-global",
    )

    reserved = step(initial, config)
    assert reserved.rule_id is RuleId.CORE_INIT_RESERVE_GLOBAL_SCOPE
    current = reserved.next_state
    unused_ref = current.machine_state.global_environment.lookup("unused")

    # Retain the installed anchor and payload before any evaluation.
    for _ in program.bindings:
        transition = step(current, config)
        assert transition.rule_id is RuleId.CORE_INIT_INSTALL_GLOBAL
        current = transition.next_state

    installed = current
    original_pending = installed.machine_state.heap.get(unused_ref).value
    assert isinstance(original_pending, PendingThunk)
    payload_ref = original_pending.payload_reference
    original_payload = installed.machine_state.heap.get(payload_ref).value
    assert isinstance(original_payload, ThunkPayload)
    unused_binding = next(
        binding for binding in program.bindings if binding.name == "unused"
    )
    assert original_payload.expression is unused_binding.rhs
    assert not original_payload.captured_locals.bindings
    assert original_payload.captured_locals.parent is None

    result = run_batch(
        installed,
        config,
        max_steps=150,
    )

    assert result.stop_reason is BatchStopReason.WHNF_PENDING

    machine = result.state.machine_state

    assert machine.control == Return(ImmediateInteger(21))
    assert machine.stack.depth == 0

    env = machine.global_environment

    base_ref = env.lookup("base")
    assert env.lookup("unused") == unused_ref
    main_ref = env.lookup("main")

    assert machine.heap.get(base_ref).value == Indirection(
        ImmediateInteger(21)
    )
    assert machine.heap.get(main_ref).value == Indirection(
        ImmediateInteger(21)
    )

    unused_pending = machine.heap.get(unused_ref).value

    assert isinstance(unused_pending, PendingThunk)
    assert unused_pending is original_pending
    assert unused_pending.payload_reference == payload_ref
    assert machine.heap.get(payload_ref).value is original_payload

    # Check every predecessor, since trace entries do not contain Force targets.
    current = installed
    for entry in result.trace:
        assert current.machine_state.control != Force(unused_ref)
        assert current.machine_state.heap.get(unused_ref).value is original_pending
        assert current.machine_state.heap.get(payload_ref).value is original_payload
        transition = step(current, config)
        assert TraceEntry.from_transition(transition) == entry
        current = transition.next_state

    rules = [entry.rule_id for entry in result.trace]

    # Only main and base require thunk entry.
    assert rules.count(RuleId.CORE_FORCE_THUNK_ENTER) == 2
    assert rules.count(RuleId.CORE_THUNK_UPDATE_WHNF) == 2

    anchors = thunk_transition_anchors(installed, config, result.trace)
    assert anchors[RuleId.CORE_FORCE_THUNK_ENTER] == [main_ref, base_ref]
    assert anchors[RuleId.CORE_THUNK_UPDATE_WHNF] == [base_ref, main_ref]

    assert RuleId.CORE_FORCE_GLOBAL_RHS not in rules


def test_first_thunk_demand_emits_demand_and_force_start():
    config = make_cbneed_config()

    initial = create_initial_core_state(
        compile_source("main = 42"),
        config,
        session_id="first-thunk-demand",
    )

    current = initial
    metrics = InstrumentationState()

    for _ in range(30):
        transition = step(current, config)
        metrics = reduce_metrics(metrics, transition)

        if transition.rule_id is RuleId.CORE_FORCE_THUNK_ENTER:
            anchor = current.machine_state.control.reference

            assert [
                event.kind
                for event in transition.semantic_events
            ] == [
                SemanticEventKind.THUNK_DEMANDED,
                SemanticEventKind.THUNK_FORCE_STARTED,
            ]

            assert all(
                event.object_id == anchor.object_id
                for event in transition.semantic_events
            )

            assert isinstance(
                current.machine_state.heap.get(anchor).value,
                PendingThunk,
            )

            assert isinstance(
                transition.next_state.machine_state.heap
                .get(anchor).value,
                EvaluatingThunk,
            )
            break

        current = transition.next_state
    else:
        pytest.fail("Thunk first force was not reached")

    assert metrics.counters.thunks_created == 1
    assert metrics.counters.thunk_demands == 1
    assert metrics.counters.thunks_forced == 1
    assert metrics.counters.thunks_never_forced == 0
