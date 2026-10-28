
"""Structural tests for Call-by-Need thunk representations."""

from dataclasses import FrozenInstanceError

import pytest

from lazy_lab.core.nodes import (
    CoreInt,
    CorePrimOp,
    CoreVar,
)
from lazy_lab.runtime.environment import Environment
from lazy_lab.runtime.references import (
    HeapReference,
    ImmediateInteger,
    ObjectId,
)
from lazy_lab.runtime.thunks import (
    EvaluatingThunk,
    PendingThunk,
    ThunkPayload,
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
