
"""Function closures with explicitly captured local references."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from lazy_lab.core.nodes import CoreLam
from lazy_lab.core.free_variables import free_variable_names

from .environment import Environment
from .heap import HeapObject
from .references import RuntimeRef


@dataclass(frozen=True, slots=True, eq=False)
class Closure(HeapObject):
    lambda_expression: CoreLam
    captured_locals: Environment

    def __post_init__(self) -> None:
        if not isinstance(self.lambda_expression, CoreLam):
            raise TypeError("Closure requires a CoreLam")

        if (
            not isinstance(self.captured_locals, Environment)
            or self.captured_locals.parent is not None
        ):
            raise ValueError(
                "captured_locals must be a standalone Environment"
            )

        if self.lambda_expression.parameter in self.captured_locals.bindings:
            raise ValueError("Closure parameter must not be captured")

    @property
    def required_slots(self) -> int:
        return 1 + len(self.captured_locals.bindings)

    def call_environment(
        self,
        argument: RuntimeRef,
        global_environment: Environment,
    ) -> Environment:
        """Prepare lexical bindings without evaluating the body."""
        return (
            global_environment
            .extend(self.captured_locals.bindings)
            .extend({self.lambda_expression.parameter: argument})
        )


def capture_closure(
    lambda_expression: CoreLam,
    definition_environment: Environment,
    free_local_names: Iterable[str],
) -> Closure:
    """Capture preidentified free local names, excluding globals."""
    if not isinstance(lambda_expression, CoreLam):
        raise TypeError("Expected CoreLam")

    names = sorted(set(free_local_names))

    if lambda_expression.parameter in names:
        raise ValueError("Cannot capture lambda parameter")

    captures = {
        name: definition_environment.lookup(name)
        for name in names
    }

    return Closure(
        lambda_expression=lambda_expression,
        captured_locals=Environment(captures),
    )

def select_free_local_names(
    lambda_expression: CoreLam,
    definition_environment: Environment,
    global_environment: Environment,
) -> tuple[str, ...]:
    """Select free names resolved in local lexical scopes.

    The definition environment must be the global environment
    or one of its descendants.

    Globals and predefined identifiers are not captured.
    The returned names are sorted for deterministic allocation.
    """
    if not isinstance(lambda_expression, CoreLam):
        raise TypeError("Expected a CoreLam")

    if not isinstance(definition_environment, Environment):
        raise TypeError("Expected a definition Environment")

    if not isinstance(global_environment, Environment):
        raise TypeError("Expected a global Environment")

    free_names = free_variable_names(lambda_expression)
    captured: set[str] = set()

    current: Environment | None = definition_environment

    # Inspect only the local scopes above the global boundary.
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

    # Every remaining free name must resolve globally or
    # through the predefined parent scope.
    for name in free_names - captured:
        global_environment.lookup(name)

    return tuple(sorted(captured))
