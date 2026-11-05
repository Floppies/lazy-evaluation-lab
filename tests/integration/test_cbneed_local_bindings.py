
import pytest

from lazy_lab.core.nodes import CoreLetRec
from lazy_lab.engine.core_machine import (
    UnsupportedTransitionError,
    create_initial_core_state,
    step,
)
from lazy_lab.pipeline import compile_source
from lazy_lab.runtime.control import EvaluateCore, InitializeLocalBindings
from lazy_lab.runtime.heap import Reserved
from lazy_lab.runtime.stack import RestoreEnvironmentFrame
from lazy_lab.runtime.thunks import PendingThunk
from lazy_lab.runtime.transitions import RuleId
from tests.integration.test_cbneed_application import make_cbneed_config


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

    # Initialization belongs to B05.6.4.
    with pytest.raises(
        UnsupportedTransitionError,
        match="Non-strict local initialization",
    ):
        step(after_state, config)

    # The rejected transition preserves the reserved state.
    assert isinstance(after.heap.get(x_ref).value, Reserved)
    assert isinstance(after.heap.get(y_ref).value, Reserved)

    # The earlier snapshot has no local reservations.
    assert (
        before.heap.current_slots
        == after.heap.current_slots - 2
    )


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
