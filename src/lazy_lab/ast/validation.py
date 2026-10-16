"""Validate AST structure and binding groups without resolving names or types."""

from __future__ import annotations

import re
from typing import NoReturn

from .nodes import (
    Application,
    BinaryOp,
    BoolLiteral,
    ConsPattern,
    Definition,
    Expr,
    FunctionEquation,
    IfExpr,
    IntLiteral,
    LambdaExpr,
    LetExpr,
    ListLiteral,
    LocalBinding,
    NilPattern,
    Node,
    Pattern,
    Program,
    SourceSpan,
    UnaryOp,
    ValueDefinition,
    Var,
    VarPattern,
)

_RESERVED = {"if", "then", "else", "let", "in", "True", "False"}
_IDENTIFIER = re.compile(r"[a-z][a-zA-Z0-9_]*")
_BINARY_OPERATORS = {"+", "-", "*", "<", "<=", ">", ">=", "==", "!=", ":"}


class ASTValidationError(ValueError):
    """An AST node violates the mini-language's structural rules."""


def _diagnostic_span(
    node: object, parent_span: SourceSpan | None = None
) -> SourceSpan | None:
    if isinstance(node, Node) and isinstance(node.span, SourceSpan):
        return node.span
    return parent_span


def _fail(message: str, span: SourceSpan | None = None) -> NoReturn:
    if span is not None:
        message = f"{span.start_line}:{span.start_column}: {message}"
    raise ASTValidationError(message)


def _require(
    condition: bool, message: str, span: SourceSpan | None = None
) -> None:
    if not condition:
        _fail(message, span)


def _check_span(
    node: Node, location: SourceSpan | None, *, allow_empty: bool = False
) -> None:
    span = node.span
    if span is None:
        return
    _require(isinstance(span, SourceSpan), "Invalid SourceSpan", location)
    positions = (span.start_line, span.start_column, span.end_line, span.end_column)
    _require(
        all(type(position) is int and position >= 1 for position in positions),
        "SourceSpan positions must be positive integers",
        location,
    )
    start = (span.start_line, span.start_column)
    end = (span.end_line, span.end_column)
    _require(end >= start, "SourceSpan ends before it starts", location)
    _require(
        allow_empty or end > start,
        "SourceSpan must not be empty for concrete syntax",
        location,
    )


def _check_identifier(name: object, span: SourceSpan | None) -> None:
    _require(
        isinstance(name, str)
        and _IDENTIFIER.fullmatch(name) is not None
        and name not in _RESERVED,
        f"Invalid identifier: {name!r}",
        span,
    )


def _check_parameters(
    parameters: object, span: SourceSpan | None, *, require_one: bool
) -> None:
    _require(isinstance(parameters, tuple), "Parameters must be a tuple", span)
    if require_one:
        _require(
            len(parameters) >= 1,
            "LambdaExpr requires at least one parameter",
            span,
        )
    seen: set[str] = set()
    for name in parameters:
        _check_identifier(name, span)
        _require(name not in seen, f"Duplicate parameter: {name!r}", span)
        seen.add(name)


def _check_pattern(
    pattern: Pattern, parent_span: SourceSpan | None = None
) -> dict[str, SourceSpan | None]:
    """Return binders and their locations for duplicate-binder diagnostics."""
    span = _diagnostic_span(pattern, parent_span)
    _require(isinstance(pattern, Pattern), "Expected a Pattern", span)
    _check_span(pattern, span)
    if isinstance(pattern, VarPattern):
        _check_identifier(pattern.name, span)
        return {pattern.name: span}
    if isinstance(pattern, NilPattern):
        return {}
    if isinstance(pattern, ConsPattern):
        for child in (pattern.head, pattern.tail):
            _require(
                isinstance(child, VarPattern),
                "ConsPattern requires two VarPattern children",
                _diagnostic_span(child, span),
            )
        head_binders = _check_pattern(pattern.head, span)
        tail_binders = _check_pattern(pattern.tail, span)
        for name, binder_span in tail_binders.items():
            _require(
                name not in head_binders,
                "Duplicate binder in ConsPattern",
                binder_span,
            )
        return head_binders | tail_binders
    _fail(f"Unsupported Pattern node: {type(pattern).__name__}", span)


def _check_expr(expr: Expr, parent_span: SourceSpan | None = None) -> None:
    span = _diagnostic_span(expr, parent_span)
    _require(isinstance(expr, Expr), "Expected an Expr", span)
    _check_span(expr, span)

    if isinstance(expr, IntLiteral):
        _require(type(expr.value) is int, "IntLiteral requires an int", span)
        _require(expr.value >= 0, "IntLiteral requires a non-negative int", span)
    elif isinstance(expr, BoolLiteral):
        _require(type(expr.value) is bool, "BoolLiteral requires a bool", span)
    elif isinstance(expr, Var):
        _check_identifier(expr.name, span)
    elif isinstance(expr, UnaryOp):
        _require(
            isinstance(expr.operator, str) and expr.operator == "-",
            "Unsupported unary operator",
            span,
        )
        _check_expr(expr.operand, span)
    elif isinstance(expr, BinaryOp):
        _require(
            isinstance(expr.operator, str) and expr.operator in _BINARY_OPERATORS,
            f"Unsupported binary operator: {expr.operator!r}",
            span,
        )
        _check_expr(expr.left, span)
        _check_expr(expr.right, span)
    elif isinstance(expr, Application):
        _check_expr(expr.function, span)
        _check_expr(expr.argument, span)
    elif isinstance(expr, LambdaExpr):
        _check_parameters(expr.parameters, span, require_one=True)
        _check_expr(expr.body, span)
    elif isinstance(expr, IfExpr):
        _check_expr(expr.condition, span)
        _check_expr(expr.then_branch, span)
        _check_expr(expr.else_branch, span)
    elif isinstance(expr, LetExpr):
        _require(isinstance(expr.bindings, tuple), "Let bindings must be a tuple", span)
        _require(len(expr.bindings) >= 1, "LetExpr requires at least one binding", span)
        seen: set[str] = set()
        for binding in expr.bindings:
            binding_span = _diagnostic_span(binding, span)
            _require(
                isinstance(binding, LocalBinding),
                "Expected a LocalBinding",
                binding_span,
            )
            _check_span(binding, binding_span)
            _check_identifier(binding.name, binding_span)
            _require(
                binding.name not in seen,
                f"Duplicate local binding: {binding.name!r}",
                binding_span,
            )
            seen.add(binding.name)
            _check_parameters(binding.parameters, binding_span, require_one=False)
            _check_expr(binding.rhs, binding_span)
        _check_expr(expr.body, span)
    elif isinstance(expr, ListLiteral):
        _require(isinstance(expr.elements, tuple), "List elements must be a tuple", span)
        for element in expr.elements:
            _check_expr(element, span)
    else:
        _fail(f"Unsupported Expr node: {type(expr).__name__}", span)


def _check_definition(
    definition: Definition, parent_span: SourceSpan | None = None
) -> None:
    span = _diagnostic_span(definition, parent_span)
    _require(isinstance(definition, Definition), "Expected a Definition", span)
    _check_span(definition, span)
    if isinstance(definition, ValueDefinition):
        _check_identifier(definition.name, span)
        _check_expr(definition.rhs, span)
    elif isinstance(definition, FunctionEquation):
        _check_identifier(definition.name, span)
        _require(
            definition.name != "main",
            "main must be a top-level value definition without parameters",
            span
        )
        _require(
            isinstance(definition.parameters, tuple),
            "FunctionEquation parameters must be a tuple",
            span,
        )
        _require(
            len(definition.parameters) >= 1,
            "FunctionEquation requires at least one parameter",
            span,
        )
        seen: set[str] = set()
        for index, pattern in enumerate(definition.parameters):
            binders = _check_pattern(pattern, span)
            if index < len(definition.parameters) - 1:
                _require(
                    isinstance(pattern, VarPattern),
                    "Constructor patterns are only allowed in the final parameter",
                    _diagnostic_span(pattern, span),
                )
            for name, binder_span in binders.items():
                _require(
                    name not in seen,
                    "Duplicate parameter binder in function equation",
                    binder_span,
                )
                seen.add(name)
        _check_expr(definition.rhs, span)
    else:
        _fail(f"Unsupported Definition node: {type(definition).__name__}", span)


def validate_expression(expression: Expr) -> None:
    """Validate expression structure without resolving names or checking types.

    Free variables and expressions that would produce runtime type errors are
    structurally valid. Invalid nodes raise ASTValidationError, using the
    offending node's span or the nearest enclosing span when available.
    """
    _check_expr(expression)


def validate_program(program: Program) -> None:
    """Validate structure, duplicate binders, equation groups and their arities.

    This does not resolve names, require main, check pattern exhaustiveness or
    redundancy, or reject recursive dependencies. Name resolution belongs to
    a later semantic stage; type errors and evaluation belong to the runtime.
    """
    span = _diagnostic_span(program)
    _require(isinstance(program, Program), "Expected a Program", span)
    _require(
        isinstance(program.definitions, tuple),
        "Program definitions must be a tuple",
        span,
    )
    _check_span(program, span, allow_empty=not program.definitions)

    seen_groups: set[str] = set()
    previous: Definition | None = None
    for definition in program.definitions:
        _check_definition(definition, span)
        definition_span = _diagnostic_span(definition, span)
        if previous is not None and definition.name == previous.name:
            _require(
                isinstance(previous, FunctionEquation)
                and isinstance(definition, FunctionEquation),
                f"Duplicate top-level definition: {definition.name!r}",
                definition_span,
            )
            _require(
                len(previous.parameters) == len(definition.parameters),
                f"Inconsistent arity for function {definition.name!r}",
                definition_span,
            )
        else:
            _require(
                definition.name not in seen_groups,
                f"Non-consecutive definitions for {definition.name!r}",
                definition_span,
            )
            seen_groups.add(definition.name)
        previous = definition
