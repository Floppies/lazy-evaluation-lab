
"""Structural tests for Call-by-Need thunk representations."""

from dataclasses import FrozenInstanceError

import pytest

from lazy_lab.core.nodes import (
    CoreInt,
    CorePrimOp,
    CoreVar,
    CoreApp,
    CoreBinding,
    CoreLam,
    CoreLetRec,
)
from lazy_lab.runtime.environment import Environment, UnboundNameError
from lazy_lab.runtime.references import (
    HeapReference,
    ImmediateInteger,
    ObjectId,
)
from lazy_lab.runtime.thunks import (
    EvaluatingThunk,
    PendingThunk,
    ThunkPayload,
    capture_thunk_payload,
)


def test_payload_preserves_expression_and_local_captures():
    expression = CorePrimOp(
        "+",
        (CoreVar("x"), CoreInt(1)),
    )

    captured = Environment({
        "x": ImmediateInteger(20),
    })

    payload = ThunkPayload(
        expression=expression,
        captured_locals=captured,
    )

    assert payload.expression is expression
    assert payload.captured_locals is captured
    assert payload.required_slots == 2
    assert payload.captured_locals.lookup("x") == (
        ImmediateInteger(20)
    )


def test_payload_without_captures_uses_one_slot():
    payload = ThunkPayload(
        expression=CoreInt(42),
        captured_locals=Environment(),
    )

    assert payload.required_slots == 1
    assert not payload.captured_locals.bindings


def test_payload_rejects_invalid_expression():
    with pytest.raises(TypeError, match="Core expression"):
        ThunkPayload(
            expression="not-core",
            captured_locals=Environment(),
        )


def test_payload_requires_standalone_environment():
    global_environment = Environment({
        "global_value": ImmediateInteger(10),
    })

    local_environment = global_environment.extend({
        "x": ImmediateInteger(20),
    })

    with pytest.raises(ValueError, match="standalone"):
        ThunkPayload(
            expression=CoreVar("x"),
            captured_locals=local_environment,
        )


@pytest.mark.parametrize(
    "anchor_type",
    [PendingThunk, EvaluatingThunk],
)
def test_anchor_uses_one_slot_and_preserves_payload_reference(
    anchor_type,
):
    payload_reference = HeapReference(ObjectId(8))

    anchor = anchor_type(payload_reference)

    assert anchor.payload_reference is payload_reference
    assert anchor.required_slots == 1


@pytest.mark.parametrize(
    "anchor_type",
    [PendingThunk, EvaluatingThunk],
)
def test_anchor_rejects_non_heap_reference(anchor_type):
    with pytest.raises(TypeError, match="heap payload reference"):
        anchor_type(ImmediateInteger(42))


def test_payload_and_anchor_are_immutable():
    payload = ThunkPayload(
        expression=CoreInt(42),
        captured_locals=Environment(),
    )
    pending = PendingThunk(HeapReference(ObjectId(8)))
    evaluating = EvaluatingThunk(HeapReference(ObjectId(8)))

    with pytest.raises(FrozenInstanceError):
        payload.expression = CoreInt(10)

    with pytest.raises(FrozenInstanceError):
        pending.payload_reference = HeapReference(ObjectId(9))

    with pytest.raises(FrozenInstanceError):
        evaluating.payload_reference = HeapReference(ObjectId(9))


def test_payload_captures_cannot_be_mutated():
    payload = ThunkPayload(
        expression=CoreVar("x"),
        captured_locals=Environment({
            "x": ImmediateInteger(20),
        }),
    )

    with pytest.raises(TypeError):
        payload.captured_locals.bindings["x"] = (
            ImmediateInteger(99)
        )

    assert payload.captured_locals.lookup("x") == (
        ImmediateInteger(20)
    )


def test_thunk_captures_nearest_free_locals_only():
    global_env = Environment({
        "x": ImmediateInteger(100),
        "global_value": ImmediateInteger(200),
    })

    outer_x = HeapReference(ObjectId(4))
    inner_x = HeapReference(ObjectId(5))
    local_y = HeapReference(ObjectId(7))

    outer_env = global_env.extend({
        "x": outer_x,
        "unused": ImmediateInteger(99),
    })

    local_env = outer_env.extend({
        "x": inner_x,
        "y": local_y,
    })

    expression = CorePrimOp(
        "+",
        (
            CoreVar("x"),
            CorePrimOp(
                "+",
                (
                    CoreVar("y"),
                    CoreVar("global_value"),
                ),
            ),
        ),
    )

    payload = capture_thunk_payload(
        expression,
        local_env,
        global_env,
    )

    assert payload.expression is expression
    assert set(payload.captured_locals.bindings) == {
        "x", "y"
    }

    assert payload.captured_locals.lookup("x") is inner_x
    assert payload.captured_locals.lookup("y") is local_y

    assert payload.captured_locals.parent is None
    assert payload.required_slots == 3

    # Preserve the original references, not copied values.
    assert payload.captured_locals.lookup("x") is not outer_x


def test_thunk_excludes_globals_and_predefined_names():
    predefined_env = Environment({
        "seq": HeapReference(ObjectId(1)),
    })

    global_env = predefined_env.extend({
        "global_value": ImmediateInteger(100),
    })

    local_x = HeapReference(ObjectId(8))
    local_env = global_env.extend({
        "x": local_x,
    })

    expression = CoreApp(
        CoreApp(
            CoreVar("seq"),
            CoreVar("x"),
        ),
        CoreVar("global_value"),
    )

    payload = capture_thunk_payload(
        expression,
        local_env,
        global_env,
    )

    assert set(payload.captured_locals.bindings) == {"x"}
    assert payload.captured_locals.lookup("x") is local_x
    assert payload.required_slots == 2


def test_thunk_respects_nested_lambda_binders():
    global_env = Environment()
    local_ref = HeapReference(ObjectId(3))

    local_env = global_env.extend({
        "external": local_ref,
        "unused": ImmediateInteger(9),
    })

    expression = CoreLam(
        "parameter",
        CorePrimOp(
            "+",
            (
                CoreVar("parameter"),
                CoreVar("external"),
            ),
        ),
    )

    payload = capture_thunk_payload(
        expression,
        local_env,
        global_env,
    )

    assert set(payload.captured_locals.bindings) == {
        "external"
    }
    assert payload.captured_locals.lookup("external") is local_ref


def test_thunk_respects_recursive_let_bindings():
    global_env = Environment()
    external_ref = HeapReference(ObjectId(12))

    local_env = global_env.extend({
        "external": external_ref,
        "x": ImmediateInteger(999),
    })

    expression = CoreLetRec(
        bindings=(
            CoreBinding("x", CoreVar("y")),
            CoreBinding("y", CoreVar("external")),
        ),
        body=CoreVar("x"),
    )

    payload = capture_thunk_payload(
        expression,
        local_env,
        global_env,
    )

    assert set(payload.captured_locals.bindings) == {
        "external"
    }

    assert payload.captured_locals.lookup("external") is (
        external_ref
    )


def test_thunk_reconstructed_scope_preserves_shadowing():
    global_env = Environment({
        "x": ImmediateInteger(100),
        "global_value": ImmediateInteger(200),
    })

    local_x = HeapReference(ObjectId(4))

    local_env = global_env.extend({
        "x": local_x,
        "unused": ImmediateInteger(9),
    })

    payload = capture_thunk_payload(
        CorePrimOp(
            "+",
            (
                CoreVar("x"),
                CoreVar("global_value"),
            ),
        ),
        local_env,
        global_env,
    )

    reconstructed = global_env.extend(
        payload.captured_locals.bindings
    )

    assert reconstructed.lookup("x") is local_x
    assert reconstructed.lookup("global_value") == (
        ImmediateInteger(200)
    )

    assert "unused" not in reconstructed.bindings


def test_thunk_capture_rejects_unbound_name():
    global_env = Environment()
    local_env = global_env.extend({})

    with pytest.raises(UnboundNameError, match="missing"):
        capture_thunk_payload(
            CoreVar("missing"),
            local_env,
            global_env,
        )


def test_thunk_capture_requires_global_ancestor():
    global_env = Environment({
        "global_value": ImmediateInteger(1),
    })

    unrelated_env = Environment({
        "x": ImmediateInteger(2),
    })

    with pytest.raises(ValueError, match="ancestor"):
        capture_thunk_payload(
            CoreVar("x"),
            unrelated_env,
            global_env,
        )


def test_thunk_capture_handles_deep_core_expression():
    global_env = Environment()
    local_ref = HeapReference(ObjectId(9))

    local_env = global_env.extend({
        "external": local_ref,
    })

    expression = CoreVar("external")

    for _ in range(2500):
        expression = CoreApp(
            expression,
            CoreInt(1),
        )

    payload = capture_thunk_payload(
        expression,
        local_env,
        global_env,
    )

    assert payload.expression is expression
    assert payload.captured_locals.lookup("external") is (
        local_ref
    )
    assert payload.required_slots == 2
