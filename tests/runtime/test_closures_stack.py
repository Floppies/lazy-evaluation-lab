import pytest

from lazy_lab.core.nodes import CoreInt, CoreLam, CoreVar
from lazy_lab.runtime.closures import capture_closure
from lazy_lab.runtime.environment import Environment
from lazy_lab.runtime.heap import Heap, Reserved
from lazy_lab.runtime.references import ImmediateInteger
from lazy_lab.runtime.stack import (
    ApplyArgumentFrame,
    ApplyFunctionFrame,
    EmptyStackError,
    Stack,
)


def test_closure_captures_definition_site():
    globals_env = Environment({
        "x": ImmediateInteger(100),
        "g": ImmediateInteger(9),
    })

    definition_env = globals_env.extend({
        "x": ImmediateInteger(20),
        "unused": ImmediateInteger(30),
    })

    closure = capture_closure(
        CoreLam("arg", CoreVar("x")),
        definition_env,
        free_local_names=("x",),
    )

    call_env = closure.call_environment(
        ImmediateInteger(3),
        globals_env,
    )

    assert call_env.lookup("x") == ImmediateInteger(20)
    assert call_env.lookup("arg") == ImmediateInteger(3)
    assert call_env.lookup("g") == ImmediateInteger(9)
    assert closure.required_slots == 2
    assert set(closure.captured_locals.bindings) == {"x"}


def test_recursive_closures_capture_reserved_references():
    heap = Heap()

    even_ref = heap.allocate(Reserved(), allocated_slots=2)
    odd_ref = heap.allocate(Reserved(), allocated_slots=2)

    recursive_env = Environment({
        "even": even_ref,
        "odd": odd_ref,
    })

    even_closure = capture_closure(
        CoreLam("n", CoreVar("odd")),
        recursive_env,
        ("odd",),
    )

    odd_closure = capture_closure(
        CoreLam("n", CoreVar("even")),
        recursive_env,
        ("even",),
    )

    heap.replace(even_ref, even_closure)
    heap.replace(odd_ref, odd_closure)

    assert even_closure.captured_locals.lookup("odd") is odd_ref
    assert odd_closure.captured_locals.lookup("even") is even_ref


def test_heap_rejects_oversized_closure():
    heap = Heap()
    reference = heap.allocate(Reserved(), allocated_slots=1)

    closure = capture_closure(
        CoreLam("y", CoreVar("x")),
        Environment({"x": ImmediateInteger(10)}),
        ("x",),
    )

    with pytest.raises(ValueError):
        heap.replace(reference, closure)

    assert isinstance(heap.get(reference).value, Reserved)
    assert heap.current_slots == 1


def test_stack_push_pop_and_clone():
    stack = Stack()
    environment = Environment()

    first = ApplyFunctionFrame(CoreInt(5), environment)
    second = ApplyArgumentFrame(ImmediateInteger(3))

    stack.push(first)
    snapshot = stack.clone()
    stack.push(second)

    assert stack.depth == 2
    assert stack.peek() is second

    assert stack.pop() is second
    assert stack.pop() is first
    assert stack.depth == 0

    assert snapshot.depth == 1
    assert snapshot.peek() is first

    with pytest.raises(EmptyStackError):
        stack.pop()


def test_lambda_parameter_is_not_captured():
    with pytest.raises(ValueError):
        capture_closure(
            CoreLam("x", CoreVar("x")),
            Environment({"x": ImmediateInteger(7)}),
            ("x",),
        )
