import pytest

from dataclasses import FrozenInstanceError

from lazy_lab.core.nodes import (
    CoreInt,
    CoreLam,
    CoreVar,
    CorePrimOp,
    CoreApp,
)
from lazy_lab.runtime.closures import (
    capture_closure,
    select_free_local_names,
    allocate_closure,
    Closure,
)
from lazy_lab.runtime.environment import Environment, UnboundNameError
from lazy_lab.runtime.heap import (
    Heap,
    Reserved,
    HeapReference,
    Indirection,
)
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


def test_selects_only_free_local_names():
    globals_env = Environment({
        "global_value": ImmediateInteger(100),
    })

    local_env = globals_env.extend({
        "x": ImmediateInteger(10),
        "unused": ImmediateInteger(20),
    })

    expression = CoreLam(
        "parameter",
        CorePrimOp(
            "+",
            (
                CoreVar("x"),
                CoreVar("global_value"),
            ),
        ),
    )

    names = select_free_local_names(
        expression,
        local_env,
        globals_env,
    )

    assert names == ("x",)

def test_local_shadow_of_global_is_captured():
    globals_env = Environment({
        "x": ImmediateInteger(100),
    })

    local_env = globals_env.extend({
        "x": ImmediateInteger(10),
    })

    expression = CoreLam("parameter", CoreVar("x"))

    names = select_free_local_names(
        expression,
        local_env,
        globals_env,
    )

    assert names == ("x",)

    closure = capture_closure(
        expression,
        local_env,
        names,
    )

    assert closure.captured_locals.lookup("x") == (
        ImmediateInteger(10)
    )

    call_env = closure.call_environment(
        ImmediateInteger(5),
        globals_env,
    )

    assert call_env.lookup("x") == ImmediateInteger(10)

def test_predefined_name_is_not_captured():
    predefined_env = Environment({
        "seq": ImmediateInteger(0),
    })

    globals_env = predefined_env.extend({
        "main": ImmediateInteger(42),
    })

    local_env = globals_env.extend({
        "x": ImmediateInteger(10),
    })

    expression = CoreLam(
        "parameter",
        CoreApp(
            CoreVar("seq"),
            CoreVar("x"),
        ),
    )

    names = select_free_local_names(
        expression,
        local_env,
        globals_env,
    )

    assert names == ("x",)

def test_lambda_parameter_is_excluded_from_capture():
    globals_env = Environment()

    local_env = globals_env.extend({
        "x": ImmediateInteger(10),
    })

    expression = CoreLam("x", CoreVar("x"))

    assert select_free_local_names(
        expression,
        local_env,
        globals_env,
    ) == ()

def test_unresolved_free_name_is_rejected():
    globals_env = Environment()
    local_env = globals_env.extend({})

    expression = CoreLam(
        "argument",
        CoreVar("missing"),
    )

    with pytest.raises(UnboundNameError):
        select_free_local_names(
            expression,
            local_env,
            globals_env,
        )

def test_capture_selection_requires_global_ancestor():
    globals_env = Environment({
        "global_value": ImmediateInteger(1),
    })

    unrelated_env = Environment({
        "x": ImmediateInteger(10),
    })

    expression = CoreLam("argument", CoreVar("x"))

    with pytest.raises(ValueError, match="ancestor"):
        select_free_local_names(
            expression,
            unrelated_env,
            globals_env,
        )

def test_capture_selection_handles_deep_environment_chain():
    globals_env = Environment({
        "global_value": ImmediateInteger(1),
    })

    local_env = globals_env

    for index in range(2500):
        local_env = local_env.extend({
            f"local{index}": ImmediateInteger(index),
        })

    expression = CoreLam(
        "argument",
        CoreApp(
            CoreVar("local2499"),
            CoreVar("global_value"),
        ),
    )

    assert select_free_local_names(
        expression,
        local_env,
        globals_env,
    ) == ("local2499",)

def test_allocate_closure_uses_exact_capture_size():
    global_env = Environment({
        "global_value": ImmediateInteger(100),
    })

    local_env = global_env.extend({
        "x": ImmediateInteger(10),
        "y": ImmediateInteger(20),
        "unused": ImmediateInteger(30),
    })

    expression = CoreLam(
        "argument",
        CorePrimOp(
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
        ),
    )

    heap = Heap()

    reference = allocate_closure(
        heap,
        expression,
        local_env,
        global_env,
    )

    cell = heap.get(reference)
    closure = cell.value

    assert isinstance(reference, HeapReference)
    assert isinstance(closure, Closure)
    assert cell.allocated_slots == 3
    assert closure.required_slots == 3

    assert set(closure.captured_locals.bindings) == {
        "x", "y"
    }

    assert closure.captured_locals.lookup("x") == (
        ImmediateInteger(10)
    )
    assert closure.captured_locals.lookup("y") == (
        ImmediateInteger(20)
    )

    assert heap.current_slots == 3
    assert heap.next_object_id == 1

def test_allocate_global_lambda_requires_one_slot():
    global_env = Environment({
        "global_value": ImmediateInteger(100),
    })

    expression = CoreLam(
        "argument",
        CorePrimOp(
            "+",
            (
                CoreVar("global_value"),
                CoreVar("argument"),
            ),
        ),
    )

    heap = Heap()

    reference = allocate_closure(
        heap,
        expression,
        global_env,
        global_env,
    )

    closure = heap.get(reference).value

    assert isinstance(closure, Closure)
    assert closure.captured_locals.bindings == {}
    assert closure.required_slots == 1
    assert heap.get(reference).allocated_slots == 1
    assert heap.current_slots == 1

    call_env = closure.call_environment(
        ImmediateInteger(5),
        global_env,
    )

    assert call_env.lookup("global_value") == (
        ImmediateInteger(100)
    )
    assert call_env.lookup("argument") == (
        ImmediateInteger(5)
    )

def test_allocate_closure_preserves_local_shadowing():
    global_env = Environment({
        "x": ImmediateInteger(100),
    })

    local_env = global_env.extend({
        "x": ImmediateInteger(10),
    })

    expression = CoreLam(
        "argument",
        CoreVar("x"),
    )

    heap = Heap()

    reference = allocate_closure(
        heap,
        expression,
        local_env,
        global_env,
    )

    closure = heap.get(reference).value

    assert isinstance(closure, Closure)
    assert closure.required_slots == 2

    call_env = closure.call_environment(
        ImmediateInteger(5),
        global_env,
    )

    assert call_env.lookup("x") == ImmediateInteger(10)
    assert global_env.lookup("x") == ImmediateInteger(100)

def test_closure_captures_heap_reference_identity():
    heap = Heap()

    captured_reference = heap.allocate(
        Reserved(),
        allocated_slots=1,
    )

    global_env = Environment()

    local_env = global_env.extend({
        "x": captured_reference,
    })

    expression = CoreLam(
        "argument",
        CoreVar("x"),
    )

    closure_reference = allocate_closure(
        heap,
        expression,
        local_env,
        global_env,
    )

    closure = heap.get(closure_reference).value

    assert isinstance(closure, Closure)
    assert closure.captured_locals.lookup("x") is (
        captured_reference
    )

    heap.replace(
        captured_reference,
        Indirection(ImmediateInteger(42)),
    )

    assert closure.captured_locals.lookup("x") is (
        captured_reference
    )

    assert heap.get(captured_reference).value == (
        Indirection(ImmediateInteger(42))
    )

def test_failed_closure_allocation_preserves_heap():
    heap = Heap()

    global_env = Environment()
    local_env = global_env.extend({})

    expression = CoreLam(
        "argument",
        CoreVar("missing"),
    )

    slots_before = heap.current_slots
    next_id_before = heap.next_object_id

    with pytest.raises(UnboundNameError):
        allocate_closure(
            heap,
            expression,
            local_env,
            global_env,
        )

    assert heap.current_slots == slots_before
    assert heap.next_object_id == next_id_before
    assert len(heap.cells) == 0

def test_closure_allocation_does_not_mutate_original_heap():
    original_heap = Heap()
    isolated_heap = original_heap.clone()

    global_env = Environment()
    expression = CoreLam(
        "x",
        CoreVar("x"),
    )

    reference = allocate_closure(
        isolated_heap,
        expression,
        global_env,
        global_env,
    )

    assert isinstance(
        isolated_heap.get(reference).value,
        Closure,
    )

    assert original_heap.current_slots == 0
    assert original_heap.next_object_id == 0
    assert len(original_heap.cells) == 0

    assert isolated_heap.current_slots == 1
