
"""Passive resolution of the Core expression in machine control."""

from __future__ import annotations

from lazy_lab.core.nodes import CoreExpr, CoreProgram
from lazy_lab.runtime.control import ApplyPrimitive, EvaluateCore
from lazy_lab.runtime.state import ExecutionState
from lazy_lab.visualizer.source_core import find_core_node_ids


def project_active_core_expression(
    state: ExecutionState,
    program: CoreProgram,
) -> dict[str, object]:
    """Identify the Core node directly represented by machine control.

    The projection never evaluates references, follows the heap,
    or guesses a source location from structural equality.
    """
    if not isinstance(state, ExecutionState):
        raise TypeError("Expected an ExecutionState")

    if not isinstance(program, CoreProgram):
        raise TypeError("Expected a CoreProgram")

    control = state.machine_state.control
    expression: CoreExpr | None = None

    if isinstance(control, EvaluateCore):
        expression = control.expression

    elif isinstance(control, ApplyPrimitive):
        expression = control.primitive

    result: dict[str, object] = {
        "control_kind": type(control).__name__,
        "expression_kind": (
            type(expression).__name__
            if expression is not None
            else None
        ),
        "core_node_id": None,
        "resolution": "no_expression",
    }

    if expression is None:
        return result

    matches = find_core_node_ids(program, expression)

    if not matches:
        result["resolution"] = "unmapped"

    elif len(matches) > 1:
        result["resolution"] = "ambiguous"

    else:
        result["core_node_id"] = matches[0]
        result["resolution"] = "resolved"

    return result
