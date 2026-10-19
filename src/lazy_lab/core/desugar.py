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

def _children(
    expr: surface.Expr,
) -> tuple[surface.Expr, ...]:
    """Return direct children in source evaluation-tree order."""
    if isinstance(
        expr,
        (surface.IntLiteral, surface.BoolLiteral, surface.Var),
    ):
        return ()

    if isinstance(expr, surface.UnaryOp):
        return (expr.operand,)

    if isinstance(expr, surface.BinaryOp):
        return (expr.left, expr.right)

    if isinstance(expr, surface.Application):
        return (expr.function, expr.argument)

    if isinstance(expr, surface.LambdaExpr):
        return (expr.body,)

    if isinstance(expr, surface.IfExpr):
        return (
            expr.condition,
            expr.then_branch,
            expr.else_branch,
        )

    if isinstance(expr, surface.LetExpr):
        return (
            *(binding.rhs for binding in expr.bindings),
            expr.body,
        )

    if isinstance(expr, surface.ListLiteral):
        return expr.elements

    raise DesugaringError(
        f"Unsupported Surface expression: {type(expr).__name__}",
        expr.span,
    )

def _take_results(
    results: list[core.CoreExpr],
    count: int,
) -> tuple[core.CoreExpr, ...]:
    """Remove the last count results, preserving their order."""
    if count == 0:
        return ()

    values = tuple(results[-count:])
    del results[-count:]

    return values

def _lower_expr(expr: surface.Expr) -> core.CoreExpr:
    pending: list[tuple[surface.Expr, bool]] = [(expr, False)]
    results: list[core.CoreExpr] = []

    while pending:
        node, expanded = pending.pop()

        children = _children(node)

        if not expanded:
            pending.append((node, True))

            for child in reversed(children):
                pending.append((child, False))

            continue

        values = _take_results(results, len(children))

        if isinstance(node, surface.IntLiteral):
            lowered = core.CoreInt(node.value, span=node.span)

        elif isinstance(node, surface.BoolLiteral):
            lowered = core.CoreBool(node.value, span=node.span)

        elif isinstance(node, surface.Var):
            lowered = core.CoreVar(node.name, span=node.span)

        elif isinstance(node, surface.UnaryOp):
            lowered = core.CorePrimOp(
                "negate",
                values,
                span=node.span,
            )

        elif isinstance(node, surface.BinaryOp):
            if node.operator == ":":
                lowered = core.CoreCon(
                    "Cons",
                    values,
                    span=node.span,
                )
            else:
                lowered = core.CorePrimOp(
                    node.operator,
                    values,
                    span=node.span,
                )

        elif isinstance(node, surface.Application):
            lowered = core.CoreApp(
                values[0],
                values[1],
                span=node.span,
            )

        elif isinstance(node, surface.LambdaExpr):
            lowered = _curry(
                node.parameters,
                values[0],
                node.span,
            )

        elif isinstance(node, surface.IfExpr):
            lowered = core.CoreIf(
                values[0],
                values[1],
                values[2],
                span=node.span,
            )

        elif isinstance(node, surface.LetExpr):
            bindings = tuple(
                core.CoreBinding(
                    name=binding.name,
                    rhs=_curry(
                        binding.parameters,
                        rhs,
                        binding.span,
                    ),
                    span=binding.span,
                )
                for binding, rhs in zip(
                    node.bindings,
                    values[:-1],
                    strict=True,
                )
            )

            lowered = core.CoreLetRec(
                bindings,
                values[-1],
                span=node.span,
            )

        elif isinstance(node, surface.ListLiteral):
            lowered = core.CoreCon(
                "Nil",
                (),
                span=node.span,
            )

            for element in reversed(values):
                lowered = core.CoreCon(
                    "Cons",
                    (element, lowered),
                    span=node.span,
                )

        else:
            raise DesugaringError(
                f"Unsupported Surface expression: "
                f"{type(node).__name__}",
                node.span,
            )

        results.append(lowered)

    return results[0]

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
