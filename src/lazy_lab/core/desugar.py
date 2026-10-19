from __future__ import annotations

from itertools import groupby

from lazy_lab.ast import nodes as surface
from lazy_lab.core import nodes as core
from lazy_lab.source import SourceSpan
from lazy_lab.core.names import FreshNameSupply

class DesugaringError(ValueError):
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

def _curry(
        parameters: tuple[str, ...],
        body: core.CoreExpr,
        span: SourceSpan | None,
    ) -> core.CoreExpr:
        """Wrap an expression in nested unary Core lambdas."""
        result = body

        for parameter in reversed(parameters):
            result = core.CoreLam(
                parameter=parameter,
                body=result,
                span=span,
            )

        return result

def _lower_expr(expr: surface.Expr) -> core.CoreExpr:
    if isinstance(expr, surface.IntLiteral):
        return core.CoreInt(
            value=expr.value,
            span=expr.span,
        )

    if isinstance(expr, surface.BoolLiteral):
        return core.CoreBool(
            value=expr.value,
            span=expr.span,
        )

    if isinstance(expr, surface.Var):
        return core.CoreVar(
            name=expr.name,
            span=expr.span,
        )

    if isinstance(expr, surface.UnaryOp):
        return core.CorePrimOp(
            operator="negate",
            arguments=(_lower_expr(expr.operand),),
            span=expr.span,
        )

    if isinstance(expr, surface.BinaryOp):
        if expr.operator == ":":
            return core.CoreCon(
                constructor="Cons",
                fields=(
                    _lower_expr(expr.left),
                    _lower_expr(expr.right),
                ),
                span=expr.span,
            )

        return core.CorePrimOp(
            operator=expr.operator,
            arguments=(
                _lower_expr(expr.left),
                _lower_expr(expr.right),
            ),
            span=expr.span,
        )

    if isinstance(expr, surface.Application):
        return core.CoreApp(
            function=_lower_expr(expr.function),
            argument=_lower_expr(expr.argument),
            span=expr.span,
        )

    if isinstance(expr, surface.LambdaExpr):
        return _curry(
            parameters=expr.parameters,
            body=_lower_expr(expr.body),
            span=expr.span,
        )

    if isinstance(expr, surface.IfExpr):
        return core.CoreIf(
            condition=_lower_expr(expr.condition),
            then_branch=_lower_expr(expr.then_branch),
            else_branch=_lower_expr(expr.else_branch),
            span=expr.span,
        )

    if isinstance(expr, surface.ListLiteral):
        result: core.CoreExpr = core.CoreCon(
            constructor="Nil",
            fields=(),
            span=expr.span,
        )

        for element in reversed(expr.elements):
            result = core.CoreCon(
                constructor="Cons",
                fields=(
                    _lower_expr(element),
                    result,
                ),
                span=expr.span,
            )

        return result

    if isinstance(expr, surface.LetExpr):
        bindings: list[core.CoreBinding] = []

        for binding in expr.bindings:
            rhs = _lower_expr(binding.rhs)

            curried_rhs = _curry(
                parameters=binding.parameters,
                body=rhs,
                span=binding.span,
            )

            bindings.append(
                core.CoreBinding(
                    name=binding.name,
                    rhs=curried_rhs,
                    span=binding.span,
                )
            )

        return core.CoreLetRec(
            bindings=tuple(bindings),
            body=_lower_expr(expr.body),
            span=expr.span,
        )

    raise DesugaringError(
        f"Unsupported Surface expression: {type(expr).__name__}",
        expr.span,
    )

def _lower_global_group(
    definitions: tuple[surface.Definition, ...],
    names: FreshNameSupply,
) -> core.CoreBinding:
    first = definitions[0]

    if isinstance(first, surface.ValueDefinition):
        if len(definitions) != 1:
            raise DesugaringError(
                "A value definition cannot have multiple equations",
                first.span,
            )

        rhs = _lower_expr(first.rhs)

    elif isinstance(first, surface.FunctionEquation):
        equations: list[surface.FunctionEquation] = []

        for definition in definitions:
            if not isinstance(definition, surface.FunctionEquation):
                raise DesugaringError(
                    "Mixed definition types in function group",
                    definition.span,
                )

            equations.append(definition)

        rhs = _lower_function_equations(
            tuple(equations),
            names,
        )

    else:
        raise DesugaringError(
            f"Unsupported global definition: {type(first).__name__}",
            first.span,
        )

    return core.CoreBinding(
        name=first.name,
        rhs=rhs,
        span=first.span,
    )

def _lower_equation_body(
    equation: surface.FunctionEquation,
    arguments: tuple[str, ...],
    *,
    include_last: bool,
) -> core.CoreExpr:
    """Lower an equation body and bind its variable parameters."""
    bindings: list[core.CoreBinding] = []

    for index, pattern in enumerate(equation.parameters):
        if index == len(arguments) - 1 and not include_last:
            continue

        if isinstance(pattern, surface.VarPattern):
            bindings.append(
                core.CoreBinding(
                    name=pattern.name,
                    rhs=core.CoreVar(
                        name=arguments[index],
                        span=pattern.span,
                    ),
                    span=pattern.span,
                )
            )

    body = _lower_expr(equation.rhs)

    if not bindings:
        return body

    return core.CoreLetRec(
        bindings=tuple(bindings),
        body=body,
        span=equation.span,
    )

def _lower_function_equations(
    equations: tuple[surface.FunctionEquation, ...],
    names: FreshNameSupply,
) -> core.CoreExpr:
    first = equations[0]

    # A variable final pattern always matches.
    # If it appears first, no constructor inspection is needed.
    first_last = first.parameters[-1]

    if isinstance(first_last, surface.VarPattern):
        parameters = tuple(
            pattern.name
            for pattern in first.parameters
        )

        return _curry(
            parameters=parameters,
            body=_lower_expr(first.rhs),
            span=first.span,
        )

    selected: list[
        tuple[surface.FunctionEquation, str | None]
    ] = []

    seen_constructors: set[str] = set()

    for equation in equations:
        pattern = equation.parameters[-1]

        if isinstance(pattern, surface.VarPattern):
            selected.append((equation, None))
            break

        if isinstance(pattern, surface.NilPattern):
            constructor = "Nil"

        elif isinstance(pattern, surface.ConsPattern):
            constructor = "Cons"

        else:
            raise DesugaringError(
                f"Unsupported pattern: {type(pattern).__name__}",
                pattern.span,
            )

        if constructor in seen_constructors:
            continue

        seen_constructors.add(constructor)
        selected.append((equation, constructor))

    arguments = tuple(
        names.fresh("arg")
        for _ in first.parameters
    )

    alternatives: list[core.CoreAlt] = []

    for equation, constructor in selected:
        pattern = equation.parameters[-1]

        if constructor is None:
            body = _lower_equation_body(
                equation,
                arguments,
                include_last=True,
            )

            alternatives.append(
                core.CoreDefaultAlt(
                    binder=names.fresh("match"),
                    body=body,
                    span=pattern.span,
                )
            )

            continue

        body = _lower_equation_body(
            equation,
            arguments,
            include_last=False,
        )

        if isinstance(pattern, surface.NilPattern):
            binders: tuple[str, ...] = ()

        elif isinstance(pattern, surface.ConsPattern):
            binders = (
                pattern.head.name,
                pattern.tail.name,
            )

        else:
            raise DesugaringError(
                "Expected a constructor pattern",
                pattern.span,
            )

        alternatives.append(
            core.CoreConAlt(
                constructor=constructor,
                binders=binders,
                body=body,
                span=pattern.span,
            )
        )

    case = core.CoreCase(
        scrutinee=core.CoreVar(
            name=arguments[-1],
            span=first.parameters[-1].span,
        ),
        alternatives=tuple(alternatives),
        span=first.parameters[-1].span,
    )

    return _curry(
        parameters=arguments,
        body=case,
        span=first.span,
    )

def lower_expression(
    expression: surface.Expr,
) -> core.CoreExpr:
    """Lower a structurally valid Surface expression to Core."""
    if not isinstance(expression, surface.Expr):
        raise TypeError("Expected a Surface Expr")

    return _lower_expr(expression)

def lower_program(
    program: surface.Program,
) -> core.CoreProgram:
    """Lower a validated Surface program into Core IR."""
    if not isinstance(program, surface.Program):
        raise TypeError("Expected a Surface Program")

    names = FreshNameSupply()
    bindings: list[core.CoreBinding] = []

    groups = groupby(
        program.definitions,
        key=lambda definition: definition.name,
    )

    for _, definitions in groups:
        group = tuple(definitions)

        bindings.append(
            _lower_global_group(group, names)
        )

    return core.CoreProgram(
        bindings=tuple(bindings),
        span=program.span,
    )
