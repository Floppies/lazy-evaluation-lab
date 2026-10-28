
"""Shared lexical capture selection for runtime values."""

from __future__ import annotations

from lazy_lab.core.free_variables import free_variable_names
from lazy_lab.core.nodes import CoreExpr

from .environment import Environment


def select_free_local_names(
    expression: CoreExpr,
    definition_environment: Environment,
    global_environment: Environment,
) -> tuple[str, ...]:
    """Select free names resolved in local lexical scopes.

    The definition environment must be the global environment
    or one of its descendants.

    Global and predefined bindings are not captured.
    Results are sorted for deterministic allocation.
    """
    if not isinstance(expression, CoreExpr):
        raise TypeError("Expected a Core expression")

    if not isinstance(definition_environment, Environment):
        raise TypeError("Expected a definition Environment")

    if not isinstance(global_environment, Environment):
        raise TypeError("Expected a global Environment")

    free_names = free_variable_names(expression)
    captured: set[str] = set()

    current: Environment | None = definition_environment

    # Only inspect lexical scopes above the global boundary.
    while current is not global_environment:
        if current is None:
            raise ValueError(
                "Global environment is not an ancestor "
                "of the definition environment"
            )

        captured.update(
            name
            for name in current.bindings
            if name in free_names
        )

        current = current.parent

    # All remaining names must be globally visible.
    for name in free_names - captured:
        global_environment.lookup(name)

    return tuple(sorted(captured))
