"""Static contracts shared by the Core evaluation strategies."""

import pytest

from lazy_lab.core.nodes import (
    CoreApp,
    CoreInt,
    CoreLetRec,
    CoreProgram,
    CoreVar,
)
from lazy_lab.pipeline import compile_source
from lazy_lab.runtime.state import (
    ExecutionConfig,
    MachineKind,
    ResultPolicy,
    Strategy,
    TraceMode,
)
from lazy_lab.semantics.name_resolution import NameResolutionError


@pytest.mark.parametrize("strategy", list(Strategy))
def test_core_accepts_each_evaluation_strategy(strategy):
    config = ExecutionConfig(
        machine_kind=MachineKind.CORE,
        strategy=strategy,
        result_policy=ResultPolicy.WHNF_ONLY,
        execution_step_limit=100,
        result_node_limit=100,
        trace_mode=TraceMode.FULL,
    )

    assert config.strategy is strategy


def test_globals_are_retained_in_source_order():
    program = compile_source(
        "main = choose 42 loop\n"
        "choose x y = x\n"
        "loop = loop"
    )

    assert isinstance(program, CoreProgram)
    assert [binding.name for binding in program.bindings] == [
        "main", "choose", "loop"
    ]

    assert isinstance(program.bindings[0].rhs, CoreApp)
    assert program.bindings[2].rhs == CoreVar("loop")


def test_unused_recursive_global_is_statically_valid():
    program = compile_source(
        "loop = loop\n"
        "main = 42"
    )

    assert program.bindings[1].rhs == CoreInt(42)


def test_local_let_preserves_recursive_group():
    program = compile_source(
        "main = let { x = y; y = 1 } in x"
    )

    expression = program.bindings[0].rhs

    assert isinstance(expression, CoreLetRec)
    assert [binding.name for binding in expression.bindings] == [
        "x", "y"
    ]
    assert expression.body == CoreVar("x")


def test_unknown_global_reference_is_rejected():
    with pytest.raises(NameResolutionError, match="missing"):
        compile_source("main = missing")
