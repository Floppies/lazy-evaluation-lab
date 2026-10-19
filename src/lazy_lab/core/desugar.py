from __future__ import annotations

from lazy_lab.ast import nodes as surface
from lazy_lab.core import nodes as core
from lazy_lab.source import SourceSpan

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

def lower_expression(
    expression: surface.Expr,
) -> core.CoreExpr:
    """Lower a structurally valid Surface expression to Core."""
    if not isinstance(expression, surface.Expr):
        raise TypeError("Expected a Surface Expr")

    return _lower_expr(expression)