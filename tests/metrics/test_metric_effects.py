
from dataclasses import FrozenInstanceError

import pytest

from lazy_lab.metrics.effects import (
    HeapAllocated,
    HeapReplaced,
    HeapBaselineRecorded,
    StackPushed,
    StackPopped,
)
from lazy_lab.runtime.references import ObjectId


def test_heap_effects_preserve_allocation_identity():
    object_id = ObjectId(3)

    allocated = HeapAllocated(
        object_id=object_id,
        allocated_slots=1,
        object_type="Reserved",
    )

    replaced = HeapReplaced(
        object_id=object_id,
        previous_object_type="Reserved",
        new_object_type="PendingThunk",
    )

    baseline = HeapBaselineRecorded(slots=12)

    assert allocated.object_id == replaced.object_id
    assert allocated.allocated_slots == 1
    assert replaced.new_object_type == "PendingThunk"
    assert baseline.slots == 12

    with pytest.raises(FrozenInstanceError):
        allocated.allocated_slots = 2


def test_stack_effects_preserve_operation_order():
    effects = (
        StackPopped("ApplyFunctionFrame"),
        StackPushed("ApplyArgumentFrame"),
    )

    assert isinstance(effects[0], StackPopped)
    assert isinstance(effects[1], StackPushed)

    assert effects[0].frame_type == "ApplyFunctionFrame"
    assert effects[1].frame_type == "ApplyArgumentFrame"

    # Two operations occurred, even though net depth is zero.
    assert len(effects) == 2
