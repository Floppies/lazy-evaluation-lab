from __future__ import annotations

from dataclasses import dataclass

from lazy_lab.ast import nodes as surface
from lazy_lab.source import SourceSpan

@dataclass(frozen=True, slots=True)
class _Visit:
    expr: surface.Expr
    inherited_span: SourceSpan | None


@dataclass(frozen=True, slots=True)
class _EnterScope:
    names: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _LeaveScope:
    names: tuple[str, ...]

_Task = _Visit | _EnterScope | _LeaveScope

class NameResolutionError(ValueError):
    """Raised when a variable reference cannot be resolved."""

    def __init__(
        self,
        message: str,
        span: SourceSpan | None = None,
    ) -> None:
        self.span = span

        if span is not None:
            message = (
                f"{span.start_line}:{span.start_column}: {message}"
            )

        super().__init__(message)

def _enter_scope(
    visible: dict[str, int],
    names: tuple[str, ...],
) -> None:
    for name in names:
        visible[name] = visible.get(name, 0) + 1


def _leave_scope(
    visible: dict[str, int],
    names: tuple[str, ...],
) -> None:
    for name in names:
        count = visible[name]

        if count == 1:
            del visible[name]
        else:
            visible[name] = count - 1

def _queue_scoped_expression(
    pending: list[_Task],
    expr: surface.Expr,
    names: tuple[str, ...],
    inherited_span: SourceSpan | None,
) -> None:
    """Schedule an expression inside a temporary lexical scope."""
    pending.append(_LeaveScope(names))
    pending.append(_Visit(expr, inherited_span))
    pending.append(_EnterScope(names))

def _equation_binders(
    equation: surface.FunctionEquation,
) -> tuple[str, ...]:
    names: list[str] = []

    for pattern in equation.parameters:
        if isinstance(pattern, surface.VarPattern):
            names.append(pattern.name)

        elif isinstance(pattern, surface.ConsPattern):
            names.append(pattern.head.name)
            names.append(pattern.tail.name)

        elif isinstance(pattern, surface.NilPattern):
            continue

        else:
            raise TypeError(
                f"Unsupported pattern: {type(pattern).__name__}"
            )

    return tuple(names)

def check_surface_names(
    program: surface.Program,
) -> None:
    """Check lexical references in a validated Surface program."""
    if not isinstance(program, surface.Program):
        raise TypeError("Expected a Surface Program")

    # All global definitions are mutually visible.
    visible: dict[str, int] = {
        definition.name: 1
        for definition in program.definitions
    }

    pending: list[_Task] = []

    for definition in reversed(program.definitions):
        if isinstance(definition, surface.FunctionEquation):
            binders = _equation_binders(definition)

        elif isinstance(definition, surface.ValueDefinition):
            binders = ()

        else:
            raise TypeError(
                f"Unsupported definition: {type(definition).__name__}"
            )

        inherited_span = (
            definition.span
            if definition.span is not None
            else program.span
        )

        _queue_scoped_expression(
            pending,
            definition.rhs,
            binders,
            inherited_span,
        )
        
    while pending:
        task = pending.pop()

        if isinstance(task, _EnterScope):
            _enter_scope(visible, task.names)
            continue

        if isinstance(task, _LeaveScope):
            _leave_scope(visible, task.names)
            continue

        node = task.expr

        span = (
            node.span
            if node.span is not None
            else task.inherited_span
        )

        if isinstance(node, surface.Var):
            if node.name not in visible:
                raise NameResolutionError(
                    f"Undefined identifier: {node.name}",
                    span,
                )
            continue

        if isinstance(
            node,
            (surface.IntLiteral, surface.BoolLiteral),
        ):
            continue

        if isinstance(node, surface.UnaryOp):
            pending.append(_Visit(node.operand, span))

        elif isinstance(node, surface.BinaryOp):
            pending.append(_Visit(node.right, span))
            pending.append(_Visit(node.left, span))

        elif isinstance(node, surface.Application):
            pending.append(_Visit(node.argument, span))
            pending.append(_Visit(node.function, span))

        elif isinstance(node, surface.IfExpr):
            pending.append(_Visit(node.else_branch, span))
            pending.append(_Visit(node.then_branch, span))
            pending.append(_Visit(node.condition, span))

        elif isinstance(node, surface.ListLiteral):
            for element in reversed(node.elements):
                pending.append(_Visit(element, span))

        elif isinstance(node, surface.LambdaExpr):
            _queue_scoped_expression(
                pending,
                node.body,
                node.parameters,
                span,
            )

        elif isinstance(node, surface.LetExpr):
            binding_names = tuple(
                binding.name
                for binding in node.bindings
            )

            # Leave the let scope after all RHSs and the body.
            pending.append(_LeaveScope(binding_names))
            pending.append(_Visit(node.body, span))

            # Every RHS sees the entire recursive let group,
            # but function parameters are local to their own RHS.
            for binding in reversed(node.bindings):
                inherited = (
                    binding.span
                    if binding.span is not None
                    else span
                )

                _queue_scoped_expression(
                    pending,
                    binding.rhs,
                    binding.parameters,
                    inherited,
                )

            # Enter the mutually recursive let scope first.
            pending.append(_EnterScope(binding_names))

        else:
            raise TypeError(
                f"Unsupported expression: {type(node).__name__}"
            )
