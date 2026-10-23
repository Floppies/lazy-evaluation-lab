import pytest

from dataclasses import FrozenInstanceError

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
    IfFrame,
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

def test_application_frame_preserves_call_site_context():
    environment = Environment({
        "x": ImmediateInteger(10),
    })
    argument = CoreVar("x")

    frame = ApplyFunctionFrame(argument, environment)

    assert frame.argument is argument
    assert frame.environment is environment
    assert frame.environment.lookup("x") == ImmediateInteger(10)


def test_argument_frame_preserves_function_reference():
    reference = ImmediateInteger(7)
    frame = ApplyArgumentFrame(reference)

    assert frame.function is reference


def test_if_frame_preserves_branches_and_environment():
    environment = Environment({
        "x": ImmediateInteger(3),
    })
    then_branch = CoreVar("x")
    else_branch = CoreInt(0)

    frame = IfFrame(
        then_branch,
        else_branch,
        environment,
    )

    assert frame.then_branch is then_branch
    assert frame.else_branch is else_branch
    assert frame.environment is environment


def test_continuation_frames_are_immutable():
    frame = ApplyFunctionFrame(
        CoreInt(5),
        Environment(),
    )

    with pytest.raises(FrozenInstanceError):
        frame.argument = CoreInt(10)


def test_nested_continuations_preserve_lifo_order():
    environment = Environment()
    outer = IfFrame(
        CoreInt(1),
        CoreInt(2),
        environment,
    )
    inner = ApplyFunctionFrame(
        CoreInt(3),
        environment,
    )

    stack = Stack()
    stack.push(outer)
    stack.push(inner)

    assert stack.depth == 2
    assert stack.pop() is inner
    assert stack.pop() is outer
    assert stack.depth == 0