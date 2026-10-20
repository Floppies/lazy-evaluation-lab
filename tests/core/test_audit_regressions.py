"""B02.8 structural and robustness checks; these do not execute Core."""

from dataclasses import fields
from itertools import product

import pytest

from lazy_lab.ast import nodes as surface
from lazy_lab.ast.validation import ASTValidationError, validate_expression, validate_program
from lazy_lab.core import nodes as core
from lazy_lab.core.desugar import DesugaringError, lower_expression, lower_program
from lazy_lab.core.names import FreshNameSupply
from lazy_lab.core.validation import (
    CoreValidationError, validate_core_expression, validate_core_program,
)
from lazy_lab.frontend.lexer import tokenize
from lazy_lab.frontend.parser import parse_expression, parse_program
from lazy_lab.frontend.tokens import TokenKind
from lazy_lab.source import SourceSpan


def _records(root):
    """Flatten dataclasses iteratively, including spans ignored by AST equality."""
    pending = [root]
    while pending:
        value = pending.pop()
        if isinstance(value, core.CoreNode):
            yield type(value).__name__
            pending.extend(reversed([getattr(value, field.name) for field in fields(value)]))
        elif isinstance(value, tuple):
            yield ("tuple", len(value))
            pending.extend(reversed(value))
        else:
            yield value


def _pipeline(source):
    assert tokenize(source)[-1].kind is TokenKind.EOF
    program = parse_program(source)
    validate_program(program)
    result = lower_program(program)
    validate_core_program(result)
    assert list(_records(result)) == list(_records(lower_program(program)))
    return result


@pytest.mark.parametrize("operator", ["+", "-", "*", "<", "<=", ">", ">=", "==", "!="])
def test_every_primitive_preserves_operands_and_spans(operator):
    expression = parse_expression(f"2 {operator} 3")
    validate_expression(expression)
    result = lower_expression(expression)
    validate_core_expression(result)
    assert result == core.CorePrimOp(operator, (core.CoreInt(2), core.CoreInt(3)))
    assert result.span == expression.span
    assert tuple(child.span for child in result.arguments) == (
        expression.left.span, expression.right.span,
    )


def test_subtraction_grouping_survives_lowering():
    result = lower_expression(parse_expression("10 - 3 - 2"))
    assert result == core.CorePrimOp("-", (
        core.CorePrimOp("-", (core.CoreInt(10), core.CoreInt(3))), core.CoreInt(2),
    ))


@pytest.mark.parametrize("kind", ["application", "let-rhs", "let-body", "lambda", "binary-right"])
def test_deep_manual_trees_validate_lower_and_preserve_every_layer(kind):
    expression = surface.IntLiteral(7)
    for _ in range(2000):
        if kind == "application":
            expression = surface.Application(surface.Var("f"), expression)
        elif kind == "let-rhs":
            expression = surface.LetExpr((surface.LocalBinding("x", (), expression),), surface.Var("x"))
        elif kind == "let-body":
            expression = surface.LetExpr((surface.LocalBinding("x", (), surface.IntLiteral(0)),), expression)
        elif kind == "lambda":
            expression = surface.LambdaExpr(("x",), expression)
        else:
            expression = surface.BinaryOp("-", surface.IntLiteral(1), expression)
    validate_expression(expression)
    program = surface.Program((surface.ValueDefinition("main", expression),))
    validate_program(program)
    result = lower_expression(expression)
    lowered_program = lower_program(program)
    validate_core_expression(result)
    validate_core_program(lowered_program)
    assert list(_records(result)) == list(_records(lowered_program.bindings[0].rhs))
    for _ in range(2000):
        if kind == "application":
            assert isinstance(result, core.CoreApp)
            assert result.function == core.CoreVar("f")
            result = result.argument
        elif kind == "let-rhs":
            assert isinstance(result, core.CoreLetRec)
            assert result.body == core.CoreVar("x")
            result = result.bindings[0].rhs
        elif kind == "let-body":
            assert isinstance(result, core.CoreLetRec)
            assert result.bindings == (core.CoreBinding("x", core.CoreInt(0)),)
            result = result.body
        elif kind == "lambda":
            assert isinstance(result, core.CoreLam)
            assert result.parameter == "x"
            result = result.body
        else:
            assert isinstance(result, core.CorePrimOp)
            assert result.operator == "-"
            assert result.arguments[0] == core.CoreInt(1)
            result = result.arguments[1]
    assert result == core.CoreInt(7)


def test_large_list_preserves_all_unevaluated_elements_in_order():
    source = "[" + ",".join(f"{i} + 1" for i in range(2000)) + "]"
    expression = parse_expression(source)
    validate_expression(expression)
    result = lower_expression(expression)
    validate_core_expression(result)
    for index in range(2000):
        assert isinstance(result, core.CoreCon)
        assert result.constructor == "Cons"
        head, result = result.fields
        assert head == core.CorePrimOp("+", (core.CoreInt(index), core.CoreInt(1)))
        assert head.span == expression.elements[index].span
    assert result == core.CoreCon("Nil", ())
    assert result.span == expression.span


@pytest.mark.parametrize("kind", ["lambda", "local", "global", "pattern"])
def test_large_parameter_lists_keep_currying_and_alias_order(kind):
    parameters = tuple(f"x{i}" for i in range(2000))
    parameter_text = " ".join(parameters)
    if kind == "lambda":
        expression = parse_expression("\\" + parameter_text + " -> x1999")
        validate_expression(expression)
        result = lower_expression(expression)
    elif kind == "local":
        expression = parse_expression(f"let {{ f {parameter_text} = x1999 }} in f")
        validate_expression(expression)
        lowered = lower_expression(expression)
        validate_core_expression(lowered)
        result = lowered.bindings[0].rhs
    else:
        suffix = " []" if kind == "pattern" else ""
        result = _pipeline(f"f {parameter_text}{suffix} = x1999").bindings[0].rhs
    validate_core_expression(result)
    for index, parameter in enumerate(parameters):
        assert isinstance(result, core.CoreLam)
        expected = f"$arg{index}" if kind == "pattern" else parameter
        assert result.parameter == expected
        result = result.body
    if kind == "pattern":
        assert isinstance(result, core.CoreLam)
        assert result.parameter == "$arg2000"
        case = result.body
        assert case.scrutinee == core.CoreVar("$arg2000")
        body = case.alternatives[0].body
        assert body.bindings == tuple(
            core.CoreBinding(name, core.CoreVar(f"$arg{index}"))
            for index, name in enumerate(parameters)
        )
        result = body.body
    assert result == core.CoreVar("x1999")


def test_large_program_groups_keep_order_and_share_one_name_supply():
    result = _pipeline("\n".join(f"f{i} x [] = x" for i in range(2000)))
    assert tuple(binding.name for binding in result.bindings) == tuple(f"f{i}" for i in range(2000))
    generated = set()
    for index, binding in enumerate(result.bindings):
        function = binding.rhs
        assert function.parameter == f"$arg{2 * index}"
        assert function.body.parameter == f"$arg{2 * index + 1}"
        generated.update((function.parameter, function.body.parameter))
        alias = function.body.body.alternatives[0].body.bindings[0]
        assert alias == core.CoreBinding("x", core.CoreVar(function.parameter))
    assert len(generated) == 4000


def test_large_equation_group_keeps_first_constructor_and_first_fallback():
    source = "\n".join(
        ["f [] = 0"] + [f"f [] = {i}" for i in range(1, 2000)]
        + ["f ys = ys", "f (h:t) = 9999"]
    )
    function = _pipeline(source).bindings[0].rhs
    nil, default = function.body.alternatives
    assert nil == core.CoreConAlt("Nil", (), core.CoreInt(0))
    assert isinstance(default, core.CoreDefaultAlt)
    assert default.body.bindings == (core.CoreBinding("ys", core.CoreVar(function.parameter)),)
    assert default.body.body == core.CoreVar("ys")


def test_alias_scopes_and_fallback_references_survive_nested_shadowing():
    result = _pipeline(
        "arg0 = 100\n"
        "match0 = 200\n"
        "f outer [] = outer\n"
        "f other (head:tail) = let { other = head } in other\n"
        "f fallback rest = (\\rest -> fallback) rest"
    )
    function = result.bindings[2].rhs
    assert (function.parameter, function.body.parameter) == ("$arg0", "$arg1")
    nil, cons, default = function.body.body.alternatives
    assert nil.body.bindings == (core.CoreBinding("outer", core.CoreVar("$arg0")),)
    assert cons.binders == ("head", "tail")
    assert cons.body.bindings == (core.CoreBinding("other", core.CoreVar("$arg0")),)
    assert cons.body.body == core.CoreLetRec(
        (core.CoreBinding("other", core.CoreVar("head")),), core.CoreVar("other"),
    )
    assert default.binder == "$match0"
    assert default.body.bindings == (
        core.CoreBinding("fallback", core.CoreVar("$arg0")),
        core.CoreBinding("rest", core.CoreVar("$arg1")),
    )
    assert default.body.body == core.CoreApp(
        core.CoreLam("rest", core.CoreVar("fallback")), core.CoreVar("rest"),
    )


def test_cons_first_duplicate_preserves_original_field_binders_and_spans():
    program = parse_program("f (h:t) = h\nf (a:b) = b\nf [] = 0")
    validate_program(program)
    result = lower_program(program)
    validate_core_program(result)
    cons, nil = result.bindings[0].rhs.body.alternatives
    assert cons == core.CoreConAlt("Cons", ("h", "t"), core.CoreVar("h"))
    assert cons.span == program.definitions[0].parameters[-1].span
    assert cons.body.span == program.definitions[0].rhs.span
    assert nil.constructor == "Nil"


def test_structurally_invalid_unreachable_equation_is_still_checked():
    program = parse_program("f x = 10\nf [] = 20")
    bad = surface.FunctionEquation("f", (), surface.IntLiteral(20))
    with pytest.raises(ASTValidationError, match="at least one parameter"):
        validate_program(surface.Program((program.definitions[0], bad)))


def test_unresolved_unreachable_rhs_is_absent_from_core():
    # Records today's lowering, without deciding B02.9's diagnostic policy.
    program = parse_program("f x = 10\nf [] = unknown")
    validate_program(program)
    assert program.definitions[1].rhs == surface.Var("unknown")
    result = lower_program(program)
    validate_core_program(result)
    assert result.bindings[0].rhs == core.CoreLam("x", core.CoreInt(10))


def test_recursive_higher_order_pipeline_retains_source_computation():
    result = _pipeline(
        "map f [] = []\n"
        "map f (x:xs) = f x : map f xs\n"
        "foldr f z [] = z\n"
        "foldr f z (x:xs) = f x (foldr f z xs)\n"
        "even n = if n == 0 then True else odd (n - 1)\n"
        "odd n = if n == 0 then False else even (n - 1)\n"
        "loop = loop\n"
        "main = let { a x = b x; b x = a x; partial = foldr (\\x y -> x + y) 0 } "
        "in partial (map (\\x -> x * 2) [1 + 2, loop])"
    )
    assert tuple(binding.name for binding in result.bindings) == (
        "map", "foldr", "even", "odd", "loop", "main",
    )
    assert result.bindings[4] == core.CoreBinding("loop", core.CoreVar("loop"))
    main = result.bindings[-1].rhs
    assert tuple(binding.name for binding in main.bindings) == ("a", "b", "partial")
    assert main.bindings[0].rhs == core.CoreLam("x", core.CoreApp(core.CoreVar("b"), core.CoreVar("x")))
    assert main.bindings[1].rhs == core.CoreLam("x", core.CoreApp(core.CoreVar("a"), core.CoreVar("x")))
    records = list(_records(main))
    assert "loop" in records and "+" in records and "*" in records


@pytest.mark.parametrize("value", [None, 1, surface.Program(())])
def test_lower_expression_rejects_wrong_root_category(value):
    with pytest.raises(TypeError, match="Expected a Surface Expr"):
        lower_expression(value)


@pytest.mark.parametrize("value", [None, 1, surface.IntLiteral(0)])
def test_lower_program_rejects_wrong_root_category(value):
    with pytest.raises(TypeError, match="Expected a Surface Program"):
        lower_program(value)


def test_unsupported_surface_expression_reports_its_span():
    span = SourceSpan(2, 3, 2, 5)
    with pytest.raises(DesugaringError, match="^2:3: Unsupported Surface expression") as error:
        lower_expression(surface.Expr(span=span))
    assert error.value.span == span


def test_fresh_names_avoid_collisions_between_overlapping_prefixes():
    names = FreshNameSupply()
    first = names.fresh("arg1")
    generated = [names.fresh("arg") for _ in range(12)]
    assert first == "$arg10"
    assert first not in generated
    assert generated[-2:] == ["$arg11", "$arg12"]
    assert names.fresh("if") == "$if0"


@pytest.mark.parametrize("container", ["program", "let"])
@pytest.mark.parametrize("span", [None, "bad", (1, 1, 1, 2)])
def test_duplicate_core_binding_with_malformed_span_uses_safe_fallback(container, span):
    parent = SourceSpan(4, 2, 4, 20)
    bindings = (core.CoreBinding("x", core.CoreInt(0)), core.CoreBinding("x", core.CoreInt(1), span=span))
    node = core.CoreProgram(bindings, span=parent) if container == "program" else core.CoreLetRec(bindings, core.CoreInt(0), span=parent)
    validate = validate_core_program if container == "program" else validate_core_expression
    with pytest.raises(CoreValidationError, match="^4:2: Duplicate Core binding") as error:
        validate(node)
    assert error.value.span == parent


@pytest.mark.parametrize("node,message", [
    (core.CoreInt(0, span=SourceSpan(True, 1, 1, 2)), "coordinates"),
    (core.CoreInt(0, span=SourceSpan(2, 1, 1, 2)), "ends before"),
    (core.CoreInt(0, span="bad"), "span type"),
    (core.CorePrimOp("+", [core.CoreInt(1), core.CoreInt(2)]), "must be a tuple"),
    (core.CoreLetRec((core.CoreInt(0),), core.CoreInt(0)), "Expected a CoreBinding"),
    (core.CoreCase(core.CoreInt(0), (core.CoreConAlt([], (), core.CoreInt(0)),)), "constructor name"),
    (core.CoreCase(core.CoreInt(0), (core.CoreInt(0),)), "Invalid CoreCase alternative"),
    (core.CoreExpr(), "Unsupported Core node"),
])
def test_core_invalid_structure_reports_validation_error(node, message):
    with pytest.raises(CoreValidationError, match=message):
        validate_core_expression(node)


@pytest.mark.parametrize("validate", [validate_core_expression, validate_core_program])
def test_core_validators_reject_wrong_root_categories(validate):
    with pytest.raises(CoreValidationError, match="Expected a Core"):
        validate(None)


def test_deep_invalid_core_descendant_preserves_ancestor_location():
    expression = core.CoreVar("Invalid")
    for _ in range(2000):
        expression = core.CoreApp(core.CoreVar("f"), expression)
    expression = core.CoreLetRec((core.CoreBinding("f", core.CoreInt(0)),), expression, span=SourceSpan(8, 3, 8, 20))
    with pytest.raises(CoreValidationError, match="^8:3: Invalid Core identifier"):
        validate_core_expression(expression)


@pytest.mark.parametrize("length", [1, 2, 3, 4])
def test_all_short_pattern_sequences_preserve_first_match_routing(length):
    # Compare static alternative routing, not execution or argument demand.
    for patterns in product(("variable", "Nil", "Cons"), repeat=length):
        equations = []
        for index, kind in enumerate(patterns):
            if kind == "variable":
                final = surface.VarPattern(f"rest{index}")
            elif kind == "Nil":
                final = surface.NilPattern()
            else:
                final = surface.ConsPattern(surface.VarPattern(f"h{index}"), surface.VarPattern(f"t{index}"))
            equations.append(surface.FunctionEquation(
                "f", (surface.VarPattern(f"x{index}"), final), surface.IntLiteral(index),
            ))
        program = surface.Program(tuple(equations))
        validate_program(program)
        result = lower_program(program)
        validate_core_program(result)
        body = result.bindings[0].rhs.body.body
        for constructor in ("Nil", "Cons"):
            expected = next((
                index for index, kind in enumerate(patterns)
                if kind in ("variable", constructor)
            ), None)
            if isinstance(body, core.CoreCase):
                alternative = next((
                    alt for alt in body.alternatives
                    if isinstance(alt, core.CoreDefaultAlt) or alt.constructor == constructor
                ), None)
                selected = alternative.body if alternative is not None else None
                if isinstance(selected, core.CoreLetRec):
                    selected = selected.body
            else:
                assert patterns[0] == "variable"
                selected = body
            assert selected == (core.CoreInt(expected) if expected is not None else None)


def test_generated_alias_case_default_and_lambda_span_policy():
    program = parse_program("f x [] = x\nf y ys = ys")
    validate_program(program)
    result = lower_program(program)
    validate_core_program(result)
    first, fallback = program.definitions
    function = result.bindings[0].rhs
    assert function.span == function.body.span == first.span
    case = function.body.body
    assert case.span == case.scrutinee.span == first.parameters[-1].span
    nil, default = case.alternatives
    assert nil.span == first.parameters[-1].span
    assert nil.body.span == first.span
    assert nil.body.bindings[0].span == nil.body.bindings[0].rhs.span == first.parameters[0].span
    assert default.span == fallback.parameters[-1].span
    assert default.body.span == fallback.span
    for binding, pattern in zip(default.body.bindings, fallback.parameters, strict=True):
        assert binding.span == binding.rhs.span == pattern.span
    assert default.body.body.span == fallback.rhs.span
