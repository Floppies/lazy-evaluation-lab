from __future__ import annotations

import re

from typing import NoReturn

from lazy_lab.source import SourceSpan

from .nodes import (
    CoreNode,
    CoreExpr,
    CoreInt,
    CoreBool,
    CoreVar,
    CoreLam,
    CoreApp,
    CorePrimOp,
    CoreIf,
    CoreBinding,
    CoreLetRec,
    CoreCon,
    CoreAlt,
    CoreConAlt,
    CoreDefaultAlt,
    CoreCase,
    CoreProgram,
)


class CoreValidationError(ValueError):
    def __init__(
        self,
        message: str,
        span: SourceSpan | None = None,
    ):
        self.span = span

        if span is not None:
            message = (
                f"{span.start_line}:"
                f"{span.start_column}: {message}"
            )

        super().__init__(message)


def _fail(
    message: str,
    span: SourceSpan | None,
) -> NoReturn:
    raise CoreValidationError(message, span)


_CORE_IDENTIFIER = re.compile(
    r"(?:[a-z][a-zA-Z0-9_]*|\$[a-z][a-zA-Z0-9_]*)\Z"
)

_RESERVED_NAMES = {"if", "then", "else", "let", "in"}

_PRIMITIVE_ARITIES = {
    "negate": 1,
    "+": 2,
    "-": 2,
    "*": 2,
    "==": 2,
    "!=": 2,
    "<": 2,
    "<=": 2,
    ">": 2,
    ">=": 2,
}

_CONSTRUCTOR_ARITIES = {
    "Nil": 0,
    "Cons": 2,
}


def _check_name(
    name: object,
    span: SourceSpan | None,
) -> None:
    if (
        type(name) is not str
        or _CORE_IDENTIFIER.fullmatch(name) is None
        or name in _RESERVED_NAMES
    ):
        _fail(f"Invalid Core identifier: {name!r}", span)


def _check_span(
    span: SourceSpan,
    inherited: SourceSpan | None,
) -> None:
    coordinates = (
        span.start_line,
        span.start_column,
        span.end_line,
        span.end_column,
    )

    if any(type(value) is not int or value < 1 for value in coordinates):
        _fail("Invalid source span coordinates", inherited)

    start = (span.start_line, span.start_column)
    end = (span.end_line, span.end_column)

    if end < start:
        _fail("Source span ends before it starts", inherited)

def _location(
    node: CoreNode,
    fallback: SourceSpan | None,
) -> SourceSpan | None:
    return node.span if isinstance(node.span, SourceSpan) else fallback

def _check_constructor(
    name: object,
    arity: int,
    span: SourceSpan | None,
) -> None:
    if type(name) is not str or name not in _CONSTRUCTOR_ARITIES:
        _fail(f"Unsupported Core constructor: {name!r}", span)

    expected = _CONSTRUCTOR_ARITIES[name]

    if arity != expected:
        _fail(
            f"Constructor {name} expects {expected} fields, "
            f"found {arity}",
            span,
        )

def _require_expr(
    value: object,
    label: str,
    span: SourceSpan | None,
) -> None:
    if not isinstance(value, CoreExpr):
        _fail(f"{label} must be a CoreExpr", span)


def _require_tuple(
    value: object,
    label: str,
    span: SourceSpan | None,
) -> None:
    if type(value) is not tuple:
        _fail(f"{label} must be a tuple", span)


def _check_bindings(
    bindings: object,
    span: SourceSpan | None,
    *,
    allow_empty: bool,
) -> None:
    _require_tuple(bindings, "Bindings", span)

    if not bindings and not allow_empty:
        _fail("CoreLetRec requires at least one binding", span)

    seen: set[str] = set()

    for binding in bindings:
        if not isinstance(binding, CoreBinding):
            _fail("Expected a CoreBinding", span)

        _check_name(binding.name, _location(binding,span))

        if binding.name in seen:
            _fail(
                f"Duplicate Core binding: {binding.name}",
                binding.span or span,
            )

        seen.add(binding.name)

def _check_node(
    node: CoreNode,
    span: SourceSpan | None,
) -> tuple[CoreNode, ...]:

    if isinstance(node, CoreInt):
        if type(node.value) is not int:
            _fail("CoreInt requires an integer", span)
        return ()

    if isinstance(node, CoreBool):
        if type(node.value) is not bool:
            _fail("CoreBool requires a boolean", span)
        return ()

    if isinstance(node, CoreVar):
        _check_name(node.name, span)
        return ()

    if isinstance(node, CoreLam):
        _check_name(node.parameter, span)
        _require_expr(node.body, "Lambda body", span)
        return (node.body,)

    if isinstance(node, CoreApp):
        _require_expr(node.function, "Application function", span)
        _require_expr(node.argument, "Application argument", span)
        return (node.function, node.argument)

    if isinstance(node, CorePrimOp):
        _require_tuple(node.arguments, "Primitive arguments", span)

        if (
            type(node.operator) is not str
            or node.operator not in _PRIMITIVE_ARITIES
        ):
            _fail(f"Unsupported primitive: {node.operator!r}", span)

        expected = _PRIMITIVE_ARITIES[node.operator]

        if len(node.arguments) != expected:
            _fail(
                f"Primitive {node.operator} expects {expected} "
                f"arguments, found {len(node.arguments)}",
                span,
            )

        for argument in node.arguments:
            _require_expr(argument, "Primitive argument", span)

        return node.arguments

    if isinstance(node, CoreIf):
        for label, expression in (
            ("Condition", node.condition),
            ("Then branch", node.then_branch),
            ("Else branch", node.else_branch),
        ):
            _require_expr(expression, label, span)

        return (
            node.condition,
            node.then_branch,
            node.else_branch,
        )

    if isinstance(node, CoreBinding):
        _check_name(node.name, span)
        _require_expr(node.rhs, "Binding RHS", span)
        return (node.rhs,)

    if isinstance(node, CoreLetRec):
        _check_bindings(node.bindings, span, allow_empty=False)
        _require_expr(node.body, "LetRec body", span)
        return (*node.bindings, node.body)

    if isinstance(node, CoreCon):
        _require_tuple(node.fields, "Constructor fields", span)
        _check_constructor(node.constructor, len(node.fields), span)

        for field in node.fields:
            _require_expr(field, "Constructor field", span)

        return node.fields

    if isinstance(node, CoreConAlt):
        _require_tuple(node.binders, "Pattern binders", span)
        _check_constructor(node.constructor, len(node.binders), span)

        seen: set[str] = set()

        for binder in node.binders:
            _check_name(binder, span)

            if binder in seen:
                _fail(f"Duplicate pattern binder: {binder}", span)

            seen.add(binder)

        _require_expr(node.body, "Alternative body", span)
        return (node.body,)

    if isinstance(node, CoreDefaultAlt):
        _check_name(node.binder, span)
        _require_expr(node.body, "Default alternative body", span)
        return (node.body,)

    if isinstance(node, CoreCase):
        _require_expr(node.scrutinee, "Case scrutinee", span)
        _require_tuple(node.alternatives, "Case alternatives", span)

        if not node.alternatives:
            _fail("CoreCase requires at least one alternative", span)

        constructors: set[str] = set()
        default_count = 0

        for alternative in node.alternatives:
            if isinstance(alternative, CoreConAlt):
                if type(alternative.constructor) is not str:
                    _fail("Invalid case constructor name", span)
                if alternative.constructor in constructors:
                    _fail(
                        f"Duplicate case constructor: "
                        f"{alternative.constructor}",
                        _location(alternative, span),
                    )
                constructors.add(alternative.constructor)

            elif isinstance(alternative, CoreDefaultAlt):
                default_count += 1

                if default_count > 1:
                    _fail("Multiple default alternatives", span)

            else:
                _fail("Invalid CoreCase alternative", span)

        return (node.scrutinee, *node.alternatives)

    if isinstance(node, CoreProgram):
        _check_bindings(node.bindings, span, allow_empty=True)
        return node.bindings

    _fail(f"Unsupported Core node: {type(node).__name__}", span)

def _walk(root: CoreNode) -> None:
    pending: list[
        tuple[CoreNode, SourceSpan | None]
    ] = [(root, None)]

    while pending:
        node, inherited_span = pending.pop()

        if not isinstance(node, CoreNode):
            _fail("Expected a CoreNode", inherited_span)

        if node.span is not None:
            if not isinstance(node.span, SourceSpan):
                _fail("Invalid source span type", inherited_span)

            _check_span(node.span, inherited_span)

        current_span = node.span or inherited_span

        children = _check_node(node, current_span)

        for child in reversed(children):
            pending.append((child, current_span))

def validate_core_expression(expression: CoreExpr) -> None:
    """Validate Core expression structure without name resolution."""
    if not isinstance(expression, CoreExpr):
        raise CoreValidationError("Expected a CoreExpr")

    _walk(expression)


def validate_core_program(program: CoreProgram) -> None:
    """Validate global Core bindings and their expression trees."""
    if not isinstance(program, CoreProgram):
        raise CoreValidationError("Expected a CoreProgram")

    _walk(program)