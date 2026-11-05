
import pytest

from lazy_lab.core.nodes import CoreLetRec
from lazy_lab.engine.core_machine import (
    UnsupportedTransitionError,
    create_initial_core_state,
    run_batch,
    step,
)
from lazy_lab.pipeline import compile_source
from lazy_lab.runtime.closures import Closure
from lazy_lab.runtime.control import EvaluateCore, InitializeLocalBindings, Return
from lazy_lab.runtime.heap import Indirection, Reserved
from lazy_lab.runtime.references import ImmediateInteger
from lazy_lab.runtime.stack import RestoreEnvironmentFrame
from lazy_lab.runtime.thunks import PendingThunk, ThunkPayload
from lazy_lab.runtime.transitions import BatchStopReason, RuleId
from tests.integration.test_cbneed_application import make_cbneed_config, thunk_transition_anchors


def advance_to_letrec_reservation(initial, config):
    """Reach the reservation transition of a CoreLetRec."""

    current = initial

    for _ in range(150):
        machine = current.machine_state
        control = machine.control

        if (
            isinstance(control, EvaluateCore)
            and isinstance(control.expression, CoreLetRec)
        ):
            transition = step(current, config)

            assert transition.rule_id is (
                RuleId.CORE_LETREC_RESERVE_SCOPE
            )

            return current, transition.next_state

        current = step(current, config).next_state

    raise AssertionError("CoreLetRec reservation was not reached")


def test_cbneed_letrec_reserves_all_bindings_before_initialization():
    program = compile_source(
        "main = let { x = y; y = 21 } in x"
    )
    config = make_cbneed_config()

    initial = create_initial_core_state(
        program,
        config,
        session_id="cbneed-letrec-reservation",
    )

    before_state, after_state = advance_to_letrec_reservation(
        initial, config
    )

    before = before_state.machine_state
    after = after_state.machine_state

    assert isinstance(
        after.control,
        InitializeLocalBindings,
    )
    assert after.control.next_index == 0

    recursive_env = after.local_environment

    assert recursive_env.parent is before.local_environment
    assert set(recursive_env.bindings) == {"x", "y"}

    x_ref = recursive_env.lookup("x")
    y_ref = recursive_env.lookup("y")

    assert x_ref != y_ref

    for reference in (x_ref, y_ref):
        cell = after.heap.get(reference)
        assert isinstance(cell.value, Reserved)
        assert cell.allocated_slots == 1

    # Exactly two stable anchors, without thunk payloads.
    assert (
        after.heap.current_slots
        == before.heap.current_slots + 2
    )
    assert (
        after.heap.next_object_id
        == before.heap.next_object_id + 2
    )

    # The caller's lexical scope is preserved.
    assert after.stack.depth == before.stack.depth + 1
    assert isinstance(
        after.stack.peek(),
        RestoreEnvironmentFrame,
    )
    assert (
        after.stack.peek().environment
        is before.local_environment
    )

    # The rejected transition preserves the reserved state.
    assert isinstance(after.heap.get(x_ref).value, Reserved)
    assert isinstance(after.heap.get(y_ref).value, Reserved)

    # The earlier snapshot has no local reservations.
    assert (
        before.heap.current_slots
        == after.heap.current_slots - 2
    )

    first = step(after_state, config)

    assert first.rule_id is RuleId.CORE_LETREC_INSTALL_THUNK

    assert isinstance(
        first.next_state.machine_state.heap.get(x_ref).value,
        PendingThunk,
    )

    # The second binding has not been initialized yet.
    assert isinstance(
        first.next_state.machine_state.heap.get(y_ref).value,
        Reserved,
    )

    # Reservation snapshot remains unchanged.
    assert isinstance(after.heap.get(x_ref).value, Reserved)
    assert isinstance(after.heap.get(y_ref).value, Reserved)


def test_cbneed_letrec_reservation_preserves_outer_scope():
    program = compile_source(
        r"main = (\x -> let { x = 99; y = x } in y) 10"
    )
    config = make_cbneed_config()

    initial = create_initial_core_state(
        program,
        config,
        session_id="cbneed-letrec-shadowing",
    )

    before_state, after_state = advance_to_letrec_reservation(
        initial, config
    )

    before = before_state.machine_state
    after = after_state.machine_state

    outer_x = before.local_environment.lookup("x")
    local_x = after.local_environment.lookup("x")
    local_y = after.local_environment.lookup("y")

    assert local_x != outer_x
    assert local_y != local_x
    assert local_y != outer_x

    # The recursive scope shadows, but does not replace,
    # the enclosing lexical environment.
    assert after.local_environment.parent is (
        before.local_environment
    )
    assert after.local_environment.parent.lookup("x") == outer_x

    assert after.stack.depth == before.stack.depth + 1

    restore = after.stack.peek()

    assert isinstance(restore, RestoreEnvironmentFrame)
    assert restore.environment is before.local_environment

    # Both local RHS bindings are still uninitialized.
    assert isinstance(
        after.heap.get(local_x).value,
        Reserved,
    )
    assert isinstance(
        after.heap.get(local_y).value,
        Reserved,
    )

    # The caller's argument thunk was not modified.
    assert isinstance(
        after.heap.get(outer_x).value,
        PendingThunk,
    )
    assert isinstance(
        before.heap.get(outer_x).value,
        PendingThunk,
    )


def test_cbneed_letrec_installs_deferred_values():
    program = compile_source(
        "main = let { x = 20 + 1; y = x + 1 } in y + x"
    )
    config = make_cbneed_config()

    initial = create_initial_core_state(
        program,
        config,
        session_id="cbneed-letrec-lazy-installation",
    )

    _, reserved_state = advance_to_letrec_reservation(
        initial, config
    )

    reserved = reserved_state.machine_state
    x_ref = reserved.local_environment.lookup("x")
    y_ref = reserved.local_environment.lookup("y")

    original_slots = reserved.heap.current_slots

    # Install x without evaluating 20 + 1.
    first = step(reserved_state, config)

    assert first.rule_id is RuleId.CORE_LETREC_INSTALL_THUNK

    first_machine = first.next_state.machine_state

    x_pending = first_machine.heap.get(x_ref).value

    assert isinstance(x_pending, PendingThunk)
    assert isinstance(
        first_machine.heap.get(y_ref).value,
        Reserved,
    )

    x_payload = first_machine.heap.get(
        x_pending.payload_reference
    ).value

    assert isinstance(x_payload, ThunkPayload)
    assert not x_payload.captured_locals.bindings

    # Install y, capturing the original x anchor.
    second = step(first.next_state, config)

    assert second.rule_id is RuleId.CORE_LETREC_INSTALL_THUNK

    second_machine = second.next_state.machine_state

    y_pending = second_machine.heap.get(y_ref).value

    assert isinstance(y_pending, PendingThunk)

    y_payload = second_machine.heap.get(
        y_pending.payload_reference
    ).value

    assert isinstance(y_payload, ThunkPayload)
    assert set(y_payload.captured_locals.bindings) == {"x"}
    assert y_payload.captured_locals.lookup("x") == x_ref

    assert second_machine.heap.get(x_ref).value is x_pending

    # x payload: 1 slot; y payload: 1 + 1 captured reference.
    assert second_machine.heap.current_slots == original_slots + 3

    # No RHS was evaluated during initialization.
    assert isinstance(
        second_machine.control,
        InitializeLocalBindings,
    )
    assert second_machine.control.next_index == 2

    body = step(second.next_state, config)

    assert body.rule_id is RuleId.CORE_LETREC_ENTER_BODY
    assert isinstance(body.next_state.machine_state.control, EvaluateCore)

    # The let body begins with both thunks pending.
    assert isinstance(
        body.next_state.machine_state.heap.get(x_ref).value,
        PendingThunk,
    )
    assert isinstance(
        body.next_state.machine_state.heap.get(y_ref).value,
        PendingThunk,
    )

    # Historical snapshots remain unchanged.
    assert isinstance(reserved.heap.get(x_ref).value, Reserved)
    assert isinstance(reserved.heap.get(y_ref).value, Reserved)
    assert isinstance(
        first_machine.heap.get(y_ref).value,
        Reserved,
    )


def test_cbneed_letrec_installs_closure_and_lazy_values():
    program = compile_source(
        "main = let { "
        "f n = x + n; "
        "x = 40 + 2; "
        "unused = 1 + True "
        "} in f 0"
    )
    config = make_cbneed_config()

    initial = create_initial_core_state(
        program,
        config,
        session_id="cbneed-letrec-mixed-initialization",
    )

    _, reserved_state = advance_to_letrec_reservation(
        initial, config
    )

    env = reserved_state.machine_state.local_environment

    f_ref = env.lookup("f")
    x_ref = env.lookup("x")
    unused_ref = env.lookup("unused")

    # Function installation occurs first.
    first = step(reserved_state, config)

    assert first.rule_id is RuleId.CORE_LETREC_INSTALL_FUNCTION

    machine = first.next_state.machine_state
    f_value = machine.heap.get(f_ref).value

    assert isinstance(f_value, Indirection)

    closure = machine.heap.get(f_value.target).value

    assert isinstance(closure, Closure)
    assert set(closure.captured_locals.bindings) == {"x"}
    assert closure.captured_locals.lookup("x") == x_ref

    # Forward reference is still reserved.
    assert isinstance(machine.heap.get(x_ref).value, Reserved)

    second = step(first.next_state, config)
    third = step(second.next_state, config)

    assert second.rule_id is RuleId.CORE_LETREC_INSTALL_THUNK
    assert third.rule_id is RuleId.CORE_LETREC_INSTALL_THUNK

    installed = third.next_state.machine_state

    assert isinstance(installed.heap.get(x_ref).value, PendingThunk)
    assert isinstance(
        installed.heap.get(unused_ref).value,
        PendingThunk,
    )

    # The actual computation can now proceed.
    result = run_batch(
        third.next_state,
        config,
        max_steps=120,
    )

    assert result.stop_reason is BatchStopReason.WHNF_PENDING

    final = result.state.machine_state

    assert final.control == Return(ImmediateInteger(42))
    assert final.stack.depth == 0

    assert final.heap.get(x_ref).value == Indirection(
        ImmediateInteger(42)
    )

    # This invalid expression is never demanded.
    assert isinstance(
        final.heap.get(unused_ref).value,
        PendingThunk,
    )

    # The function binding retains its stable indirection.
    assert final.heap.get(f_ref).value == f_value


def test_cbneed_local_forward_aliases_share_result():
    program = compile_source(
        "main = let { "
        "x = y; "
        "y = base; "
        "base = 40 + 2 "
        "} in x + y"
    )
    config = make_cbneed_config()

    initial = create_initial_core_state(
        program, config,
        session_id="cbneed-local-aliases",
    )

    _, reserved_state = advance_to_letrec_reservation(
        initial, config
    )

    reserved = reserved_state.machine_state
    env = reserved.local_environment

    x_ref = env.lookup("x")
    y_ref = env.lookup("y")
    base_ref = env.lookup("base")
    main_ref = reserved.global_environment.lookup("main")

    assert len({x_ref, y_ref, base_ref}) == 3

    result = run_batch(
        reserved_state, config, max_steps=180
    )

    assert result.stop_reason is BatchStopReason.WHNF_PENDING
    machine = result.state.machine_state
    assert machine.control == Return(ImmediateInteger(84))

    for ref in (x_ref, y_ref, base_ref):
        assert machine.heap.get(ref).value == Indirection(
            ImmediateInteger(42)
        )

    anchors = thunk_transition_anchors(
        reserved_state, config, result.trace
    )

    assert anchors[RuleId.CORE_FORCE_THUNK_ENTER] == [
        x_ref, y_ref, base_ref
    ]
    assert anchors[RuleId.CORE_THUNK_UPDATE_WHNF] == [
        base_ref, y_ref, x_ref, main_ref
    ]

    rules = [entry.rule_id for entry in result.trace]

    # The base addition and the final x + y.
    assert rules.count(RuleId.CORE_PRIM_EXECUTE) == 2

    # Historical reservations remain untouched.
    for ref in (x_ref, y_ref, base_ref):
        assert isinstance(reserved.heap.get(ref).value, Reserved)


def test_cbneed_mutually_recursive_local_closures():
    program = compile_source(
        "main = let { "
        "f x = if x then 1 else g True; "
        "g y = if y then 2 else f True "
        "} in f False"
    )
    config = make_cbneed_config()

    initial = create_initial_core_state(
        program, config,
        session_id="cbneed-mutually-recursive-functions",
    )

    _, reserved_state = advance_to_letrec_reservation(
        initial, config
    )

    env = reserved_state.machine_state.local_environment
    f_ref = env.lookup("f")
    g_ref = env.lookup("g")

    # f is installed before g.
    first = step(reserved_state, config)
    assert first.rule_id is RuleId.CORE_LETREC_INSTALL_FUNCTION

    first_heap = first.next_state.machine_state.heap
    f_alias = first_heap.get(f_ref).value

    assert isinstance(f_alias, Indirection)
    f_closure = first_heap.get(f_alias.target).value

    assert isinstance(f_closure, Closure)
    assert f_closure.captured_locals.lookup("g") == g_ref
    assert isinstance(first_heap.get(g_ref).value, Reserved)

    # g can capture the already reserved f reference.
    second = step(first.next_state, config)
    assert second.rule_id is RuleId.CORE_LETREC_INSTALL_FUNCTION

    second_heap = second.next_state.machine_state.heap
    g_alias = second_heap.get(g_ref).value

    assert isinstance(g_alias, Indirection)
    g_closure = second_heap.get(g_alias.target).value

    assert isinstance(g_closure, Closure)
    assert g_closure.captured_locals.lookup("f") == f_ref

    # Both functions are now available, without having
    # executed either body.
    result = run_batch(
        second.next_state, config, max_steps=180
    )

    assert result.stop_reason is BatchStopReason.WHNF_PENDING

    final = result.state.machine_state
    assert final.control == Return(ImmediateInteger(2))
    assert final.stack.depth == 0

    # Stable binding addresses still point to the same closures.
    assert final.heap.get(f_ref).value is f_alias
    assert final.heap.get(g_ref).value is g_alias

    rules = [entry.rule_id for entry in result.trace]

    assert rules.count(RuleId.CORE_CBNEED_ENTER_BODY) == 2
    assert RuleId.CORE_LETREC_EVAL_VALUE not in rules


def test_cbneed_nested_shadowing_preserves_lexical_scope():
    program = compile_source(
        "main = let { "
        "x = 10; "
        "f y = x + y "
        "} in let { x = 20 } in f x"
    )
    config = make_cbneed_config()

    initial = create_initial_core_state(
        program, config,
        session_id="cbneed-nested-shadowing",
    )

    _, outer_state = advance_to_letrec_reservation(
        initial, config
    )

    outer_env = outer_state.machine_state.local_environment
    outer_x = outer_env.lookup("x")
    f_ref = outer_env.lookup("f")

    # Advance through the outer initialization until
    # the nested CoreLetRec is reserved.
    _, inner_state = advance_to_letrec_reservation(
        outer_state, config
    )

    inner = inner_state.machine_state
    inner_x = inner.local_environment.lookup("x")

    assert inner_x != outer_x

    # f was defined in the outer scope.
    f_alias = inner.heap.get(f_ref).value
    assert isinstance(f_alias, Indirection)

    closure = inner.heap.get(f_alias.target).value
    assert isinstance(closure, Closure)

    assert closure.captured_locals.lookup("x") == outer_x

    # Continue evaluating the inner let body.
    result = run_batch(
        inner_state, config, max_steps=180
    )

    assert result.stop_reason is BatchStopReason.WHNF_PENDING

    final = result.state.machine_state

    assert final.control == Return(ImmediateInteger(30))
    assert final.stack.depth == 0

    assert final.heap.get(outer_x).value == Indirection(
        ImmediateInteger(10)
    )
    assert final.heap.get(inner_x).value == Indirection(
        ImmediateInteger(20)
    )

    # The captured reference was not rebound to inner_x.
    assert closure.captured_locals.lookup("x") == outer_x

def test_cbneed_local_unused_recursion_not_demanded():
    program = compile_source(
        "main = let { "
        "unused = unused;"
        "answer = 42"
        "} in answer"
    )
    config = make_cbneed_config()

    initial = create_initial_core_state(
        program, config,
        session_id="cbneed-nested-shadowing",
    )

    _, unused_state = advance_to_letrec_reservation(
        initial, config
    )

    unused_env = unused_state.machine_state.local_environment
    unused_ref = unused_env.lookup("unused")
    answer_ref = unused_env.lookup("answer")

    result = run_batch(
        unused_state, config, max_steps=180
    )

    assert result.stop_reason is BatchStopReason.WHNF_PENDING

    final = result.state.machine_state
    assert final.control == Return(ImmediateInteger(42))
    assert final.stack.depth == 0

    assert isinstance(final.heap.get(unused_ref).value,PendingThunk)
    assert final.heap.get(answer_ref).value == Indirection(ImmediateInteger(42))

    anchors = thunk_transition_anchors(
        unused_state, config, result.trace
    )
    main_ref = unused_state.machine_state.global_environment.lookup("main")

    assert anchors[RuleId.CORE_FORCE_THUNK_ENTER] == [answer_ref]
    assert anchors[RuleId.CORE_THUNK_UPDATE_WHNF] == [answer_ref, main_ref]

    assert unused_ref not in anchors[RuleId.CORE_FORCE_THUNK_ENTER]
    assert unused_ref not in anchors[RuleId.CORE_THUNK_UPDATE_WHNF]