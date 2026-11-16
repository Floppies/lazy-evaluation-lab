
import pytest

from lazy_lab.core.nodes import CoreVar
from lazy_lab.metrics.effects import HeapAllocated, HeapReplaced, StackPopped, StackPushed
from lazy_lab.metrics.events import SemanticEventKind
from lazy_lab.metrics.recording import HeapEffectRecorder, SemanticEventRecorder, StackEffectRecorder
from lazy_lab.runtime.references import ObjectId
from lazy_lab.runtime.stack import Stack
from lazy_lab.source import OriginKind, SourceSpan


def test_recorder_preserves_event_order_and_provenance():
    recorder = SemanticEventRecorder()

    expression = CoreVar(
        "x",
        span=SourceSpan(1, 1, 1, 2),
        origin=OriginKind.GENERATED,
    )

    recorder.emit(
        SemanticEventKind.VARIABLE_LOOKED_UP,
        node=expression,
    )

    recorder.emit(
        SemanticEventKind.THUNK_DEMANDED,
        object_id=ObjectId(7),
    )

    recorded = recorder.freeze()

    assert isinstance(recorded, tuple)
    assert len(recorded) == 2

    assert recorded[0].origin.kind is OriginKind.GENERATED
    assert recorded[0].origin.source_spans == (
        expression.span,
    )

    assert recorded[1].object_id == ObjectId(7)
    assert recorded[1].origin.kind is OriginKind.UNKNOWN


def test_heap_effect_recorder_preserves_order():
    recorder = HeapEffectRecorder()

    allocation = HeapAllocated(
        object_id=ObjectId(0),
        allocated_slots=2,
        object_type="ThunkPayload",
    )

    replacement = HeapReplaced(
        object_id=ObjectId(0),
        previous_object_type="Reserved",
        new_object_type="PendingThunk",
    )

    recorder.record(allocation)
    frozen = recorder.freeze()

    recorder.record(replacement)

    assert frozen == (allocation,)
    assert recorder.freeze() == (
        allocation,
        replacement,
    )


def test_stack_effect_recorder_preserves_order():
    recorder = StackEffectRecorder()

    pushed = StackPushed("ApplyFunctionFrame")
    popped = StackPopped("ApplyFunctionFrame")

    recorder.record(pushed)
    snapshot = recorder.freeze()

    recorder.record(popped)

    assert snapshot == (pushed,)
    assert recorder.freeze() == (pushed, popped)


def test_stack_effect_capture_is_isolated_and_released():
    stack = Stack()
    observed = []

    with stack.capture_effects(observed.append):
        cloned = stack.clone()

        # A clone must not inherit the active observer.
        with cloned.capture_effects(observed.append):
            pass

        with pytest.raises(RuntimeError):
            with stack.capture_effects(observed.append):
                pass

    # The original observer was released.
    with stack.capture_effects(observed.append):
        pass

    # Exceptions must also release the observer.
    with pytest.raises(ValueError):
        with stack.capture_effects(observed.append):
            raise ValueError("test failure")

    with stack.capture_effects(observed.append):
        pass
