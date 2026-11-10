from lazy_lab.core.nodes import CoreInt
from lazy_lab.runtime.constructors import allocate_constructor
from lazy_lab.runtime.global_bindings import PendingGlobal
from lazy_lab.runtime.heap import Heap
from lazy_lab.runtime.materialization import (
    advance_materialization,
    resume_materialization,
    start_materialization,
)
from lazy_lab.runtime.observation import (
    CanonicalConstructor,
    CanonicalInteger,
)
from lazy_lab.runtime.references import ImmediateInteger


def test_materialization_traverses_depth_first_left_to_right():
    heap = Heap()

    nil = allocate_constructor(heap, "Nil", ())
    inner = allocate_constructor(
        heap, "Cons", (ImmediateInteger(2), nil)
    )
    outer = allocate_constructor(
        heap, "Cons", (ImmediateInteger(1), inner)
    )

    state = start_materialization(outer)
    visited = []

    for _ in range(10):
        if state.completed_value is not None:
            break

        visited.append(state.pending_reference)
        state = advance_materialization(heap, state)

        assert not state.awaiting_whnf
    else:
        raise AssertionError("Materialization did not finish")

    assert visited == [
        outer,
        ImmediateInteger(1),
        inner,
        ImmediateInteger(2),
        nil,
    ]

    assert state.visited_nodes == 5

    assert state.completed_value == CanonicalConstructor(
        "Cons",
        (
            CanonicalInteger(1),
            CanonicalConstructor(
                "Cons",
                (
                    CanonicalInteger(2),
                    CanonicalConstructor("Nil", ()),
                ),
            ),
        ),
    )


def test_materialization_pauses_on_unresolved_field():
    heap = Heap()

    pending = heap.allocate(
        PendingGlobal(CoreInt(7)),
        allocated_slots=1,
    )
    nil = allocate_constructor(heap, "Nil", ())
    root = allocate_constructor(heap, "Cons", (pending, nil))

    original_cells = dict(heap.cells)

    state = start_materialization(root)
    state = advance_materialization(heap, state)

    assert state.pending_reference == pending

    paused = advance_materialization(heap, state)

    assert paused.awaiting_whnf
    assert paused.pending_reference == pending
    assert paused.visited_nodes == 1
    assert dict(heap.cells) == original_cells

    # Simulate the reference returned by a future Force transition.
    resumed = resume_materialization(
        paused,
        ImmediateInteger(7),
    )

    assert not resumed.awaiting_whnf

    resumed = advance_materialization(heap, resumed)
    assert resumed.pending_reference == nil

    finished = advance_materialization(heap, resumed)

    assert finished.completed_value == CanonicalConstructor(
        "Cons",
        (
            CanonicalInteger(7),
            CanonicalConstructor("Nil", ()),
        ),
    )

    assert dict(heap.cells) == original_cells