"""Iterative free-variable analysis for Core expressions."""

from __future__ import annotations

from lazy_lab.core.nodes import (
    CoreApp,
    CoreBool,
    CoreCase,
    CoreCon,
    CoreConAlt,
    CoreDefaultAlt,
    CoreExpr,
    CoreIf,
    CoreInt,
    CoreLam,
    CoreLetRec,
    CorePrimOp,
    CoreVar,
)


def free_variable_names(expression: CoreExpr) -> frozenset[str]:
    """Return names free relative to the supplied Core expression.

    Uses an explicit traversal stack and lexical scope counters.
    Global and predefined names are not filtered at this stage.
    """
    if not isinstance(expression, CoreExpr):
        raise TypeError("Expected a Core expression")

    free: set[str] = set()
    bound_counts: dict[str, int] = {}

    pending: list[tuple[str, CoreExpr | tuple[str, ...]]] = [
        ("visit", expression)
    ]

    def schedule_scope(
        names: tuple[str, ...],
        children: tuple[CoreExpr, ...],
    ) -> None:
        """Schedule a scope without entering it recursively."""
        pending.append(("leave", names))

        for child in reversed(children):
            pending.append(("visit", child))

        pending.append(("enter", names))

    while pending:
        action, payload = pending.pop()

        if action == "enter":
            assert isinstance(payload, tuple)

            for name in payload:
                bound_counts[name] = (
                    bound_counts.get(name, 0) + 1
                )

            continue

        if action == "leave":
            assert isinstance(payload, tuple)

            for name in payload:
                remaining = bound_counts[name] - 1

                if remaining == 0:
                    del bound_counts[name]
                else:
                    bound_counts[name] = remaining

            continue

        if action != "visit":
            raise RuntimeError(
                f"Unknown traversal action: {action}"
            )

        node = payload
        assert isinstance(node, CoreExpr)

        if isinstance(node, (CoreInt, CoreBool)):
            continue

        if isinstance(node, CoreVar):
            if node.name not in bound_counts:
                free.add(node.name)
            continue

        if isinstance(node, CoreLam):
            schedule_scope(
                (node.parameter,),
                (node.body,),
            )
            continue

        if isinstance(node, CoreApp):
            pending.append(("visit", node.argument))
            pending.append(("visit", node.function))
            continue

        if isinstance(node, CorePrimOp):
            for argument in reversed(node.arguments):
                pending.append(("visit", argument))
            continue

        if isinstance(node, CoreIf):
            pending.append(("visit", node.else_branch))
            pending.append(("visit", node.then_branch))
            pending.append(("visit", node.condition))
            continue

        if isinstance(node, CoreCon):
            for field in reversed(node.fields):
                pending.append(("visit", field))
            continue

        if isinstance(node, CoreLetRec):
            names = tuple(
                binding.name for binding in node.bindings
            )

            # Every recursive binder is visible in every RHS
            # and in the body of the letrec.
            children = (
                tuple(binding.rhs for binding in node.bindings)
                + (node.body,)
            )

            schedule_scope(names, children)
            continue

        if isinstance(node, CoreCase):
            # Alternative binders are visible only in their
            # own alternative body, never in the scrutinee
            # or in another alternative.
            for alternative in reversed(node.alternatives):
                if isinstance(alternative, CoreConAlt):
                    names = alternative.binders
                elif isinstance(alternative, CoreDefaultAlt):
                    names = (alternative.binder,)
                else:
                    raise TypeError(
                        "Unsupported Core case alternative"
                    )

                schedule_scope(
                    names,
                    (alternative.body,),
                )

            pending.append(("visit", node.scrutinee))
            continue

        raise TypeError(
            f"Unsupported Core expression: {type(node).__name__}"
        )

    return frozenset(free)
