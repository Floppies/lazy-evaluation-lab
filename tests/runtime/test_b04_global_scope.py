
"""Predefined and recursive global scope reservation."""

import pytest

from lazy_lab.core.nodes import CoreBinding, CoreInt
from lazy_lab.engine.core_machine import _reserve_global_scope
from lazy_lab.pipeline import compile_source
from lazy_lab.runtime.environment import (
    UnboundNameError,
)
from lazy_lab.runtime.heap import Heap, Reserved
from lazy_lab.runtime.predefined import PredefinedFunction
from lazy_lab.runtime.references import HeapReference


def test_every_global_receives_a_stable_address():
    program = compile_source(
        "first = second\n"
        "second = 42\n"
        "main = first"
    )

    heap = Heap()
    environment = _reserve_global_scope(
        heap,
        program.bindings,
    )

    assert set(environment.bindings) == {
        "first", "second", "main"
    }

    references = [
        environment.lookup(name)
        for name in ("first", "second", "main")
    ]

    assert all(
        isinstance(reference, HeapReference)
        for reference in references
    )

    assert len(set(references)) == 3

    assert all(
        isinstance(heap.get(reference).value, Reserved)
        for reference in references
    )


def test_global_rhs_is_not_evaluated():
    program = compile_source(
        "loop = loop\n"
        "main = 42"
    )

    heap = Heap()
    environment = _reserve_global_scope(
        heap,
        program.bindings,
    )

    assert isinstance(
        heap.get(environment.lookup("loop")).value,
        Reserved,
    )

    assert isinstance(
        heap.get(environment.lookup("main")).value,
        Reserved,
    )


def test_predefined_function_is_in_outer_scope():
    program = compile_source("main = seq 1 2")

    heap = Heap()
    environment = _reserve_global_scope(
        heap,
        program.bindings,
    )

    assert "seq" not in environment.bindings
    assert environment.parent is not None

    reference = environment.lookup("seq")
    builtin = heap.get(reference).value

    assert isinstance(builtin, PredefinedFunction)
    assert builtin.name == "seq"
    assert builtin.arity == 2
    assert builtin.required_slots == 1


def test_user_global_shadows_predefined_seq():
    program = compile_source(
        "seq x y = x\n"
        "main = seq 1 2"
    )

    heap = Heap()
    environment = _reserve_global_scope(
        heap,
        program.bindings,
    )

    global_reference = environment.lookup("seq")
    predefined_reference = environment.parent.lookup("seq")

    assert global_reference != predefined_reference
    assert isinstance(
        heap.get(global_reference).value,
        Reserved,
    )
    assert isinstance(
        heap.get(predefined_reference).value,
        PredefinedFunction,
    )


def test_reservation_uses_exact_abstract_slots():
    program = compile_source(
        "a = 1\n"
        "b = 2\n"
        "main = a"
    )

    heap = Heap()
    environment = _reserve_global_scope(
        heap,
        program.bindings,
    )

    assert len(environment.bindings) == 3
    assert heap.current_slots == 4
    assert heap.next_object_id == 4


def test_missing_name_still_raises():
    program = compile_source("main = 42")

    heap = Heap()
    environment = _reserve_global_scope(
        heap,
        program.bindings,
    )

    with pytest.raises(UnboundNameError):
        environment.lookup("missing")


def test_duplicate_globals_are_rejected_before_allocation():
    bindings = (
        CoreBinding("x", CoreInt(1)),
        CoreBinding("x", CoreInt(2)),
    )

    heap = Heap()

    with pytest.raises(ValueError, match="Duplicate"):
        _reserve_global_scope(heap, bindings)

    assert heap.current_slots == 0


def test_unknown_predefined_function_is_rejected():
    with pytest.raises(ValueError):
        PredefinedFunction("unknown")
