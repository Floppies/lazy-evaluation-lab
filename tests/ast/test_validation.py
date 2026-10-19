"""Structural validation tests; name resolution and evaluation are separate stages."""

from dataclasses import replace

import pytest

from lazy_lab.ast.nodes import (
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
from lazy_lab.ast.validation import (
    ASTValidationError,
    validate_expression,
    validate_program,
)

from lazy_lab.frontend.parser import parse_expression


def _validate(tree):
    """Exercise only public validators, selecting the appropriate entry point."""
    if isinstance(tree, Program):
        validate_program(tree)
    else:
        validate_expression(tree)


def _equation_program(parameters):
    return Program((FunctionEquation("f", parameters, IntLiteral(0)),))


def test_valid_map_program():
    program = Program(
        (
            FunctionEquation("map", (VarPattern("f"), NilPattern()), ListLiteral(())),
            FunctionEquation(
                "map",
                (VarPattern("f"), ConsPattern(VarPattern("x"), VarPattern("xs"))),
                BinaryOp(
                    ":",
                    Application(Var("f"), Var("x")),
                    Application(Application(Var("map"), Var("f")), Var("xs")),
                ),
            ),
            FunctionEquation(
                "double",
                (VarPattern("x"),),
                BinaryOp("*", Var("x"), IntLiteral(2)),
            ),
            ValueDefinition(
                "main",
                Application(
                    Application(Var("map"), Var("double")),
                    ListLiteral((IntLiteral(1),)),
                ),
            ),
        )
    )
    validate_program(program)


def test_valid_empty_program():
    validate_program(Program(()))


def test_program_does_not_require_main():
    validate_program(Program((ValueDefinition("answer", IntLiteral(42)),)))


@pytest.mark.parametrize(
    "tree",
    [
        pytest.param(Var("unknown"), id="standalone-free-variable"),
        pytest.param(
            Program((ValueDefinition("answer", Var("unknown")),)),
            id="unresolved-program-name",
        ),
    ],
)
def test_structural_validation_does_not_resolve_names(tree):
    _validate(tree)


@pytest.mark.parametrize(
    "expr",
    [
        pytest.param(IfExpr(IntLiteral(1), IntLiteral(2), IntLiteral(3)), id="if-type"),
        pytest.param(BinaryOp("+", BoolLiteral(True), IntLiteral(1)), id="primitive-type"),
        pytest.param(Application(IntLiteral(1), IntLiteral(2)), id="non-function"),
        pytest.param(BinaryOp(":", IntLiteral(1), IntLiteral(2)), id="cons-tail-type"),
        pytest.param(ListLiteral((IntLiteral(1), BoolLiteral(False))), id="mixed-list"),
    ],
)
def test_structural_validation_does_not_check_runtime_types(expr):
    validate_expression(expr)


@pytest.mark.parametrize(
    "tree",
    [
        pytest.param(
            Program((ValueDefinition("loop", Var("loop")),)),
            id="top-level-self-recursion",
        ),
        pytest.param(
            Program(
                (
                    FunctionEquation("f", (VarPattern("x"),), Application(Var("g"), Var("x"))),
                    FunctionEquation("g", (VarPattern("x"),), Application(Var("f"), Var("x"))),
                )
            ),
            id="top-level-mutual-recursion",
        ),
        pytest.param(
            LetExpr((LocalBinding("x", (), Var("x")),), Var("x")),
            id="local-self-recursion",
        ),
        pytest.param(
            LetExpr(
                (LocalBinding("x", (), Var("y")), LocalBinding("y", (), Var("x"))),
                Var("x"),
            ),
            id="local-mutual-recursion",
        ),
    ],
)
def test_recursive_dependencies_are_structurally_valid(tree):
    _validate(tree)


def test_nested_scopes_may_shadow_outer_names():
    validate_program(
        Program(
            (
                ValueDefinition("x", IntLiteral(1)),
                FunctionEquation(
                    "f",
                    (VarPattern("x"),),
                    LambdaExpr(
                        ("x",),
                        LetExpr((LocalBinding("x", (), IntLiteral(2)),), Var("x")),
                    ),
                ),
            )
        )
    )


def test_local_function_parameter_may_shadow_binding_name():
    validate_expression(
        LetExpr(
            (LocalBinding("f", ("f",), Var("f")),),
            Application(Var("f"), IntLiteral(1)),
        )
    )


@pytest.mark.parametrize(
    "build",
    [
        pytest.param(lambda parameters: LambdaExpr(parameters, Var("x")), id="lambda"),
        pytest.param(
            lambda parameters: LetExpr(
                (LocalBinding("f", parameters, Var("x")),), Var("f")
            ),
            id="local-function",
        ),
    ],
)
def test_multiple_identifier_parameters_are_valid(build):
    validate_expression(build(("x", "y")))


@pytest.mark.parametrize(
    "build",
    [
        pytest.param(lambda parameter: LambdaExpr((parameter,), IntLiteral(0)), id="lambda"),
        pytest.param(
            lambda parameter: LetExpr(
                (LocalBinding("f", (parameter,), IntLiteral(0)),), Var("f")
            ),
            id="local-function",
        ),
    ],
)
@pytest.mark.parametrize(
    "parameter",
    [
        pytest.param(None, id="none"),
        pytest.param(1, id="integer"),
        pytest.param(VarPattern("x"), id="variable-pattern"),
        pytest.param(NilPattern(), id="nil-pattern"),
        pytest.param(ConsPattern(VarPattern("x"), VarPattern("xs")), id="cons-pattern"),
    ],
)
def test_lambda_and_local_parameters_require_identifier_strings(build, parameter):
    with pytest.raises(ASTValidationError, match="Invalid identifier"):
        validate_expression(build(parameter))


@pytest.mark.parametrize(
    "parameters",
    [
        pytest.param((NilPattern(),), id="non-exhaustive"),
        pytest.param(
            (VarPattern("xs"), NilPattern(), ConsPattern(VarPattern("x"), VarPattern("xs"))),
            id="variable-before-constructors",
        ),
        pytest.param((NilPattern(), NilPattern()), id="redundant-equation"),
        pytest.param((VarPattern("x"), VarPattern("x")), id="binder-reuse-across-equations"),
    ],
)
def test_exhaustiveness_and_redundancy_are_not_required(parameters):
    validate_program(
        Program(tuple(FunctionEquation("f", (pattern,), IntLiteral(0)) for pattern in parameters))
    )


@pytest.mark.parametrize("value", [0, 1, 10**100], ids=["zero", "one", "arbitrary-precision"])
def test_valid_integer_literals(value):
    validate_expression(IntLiteral(value))


@pytest.mark.parametrize(
    "value", [True, False, 1.0, "1", None], ids=["true", "false", "float", "string", "none"]
)
def test_integer_literal_requires_exact_int_type(value):
    with pytest.raises(ASTValidationError, match="requires an int"):
        validate_expression(IntLiteral(value))


def test_negative_integer_requires_unary_negation():
    with pytest.raises(ASTValidationError, match="non-negative"):
        validate_expression(IntLiteral(-1))
    validate_expression(UnaryOp("-", IntLiteral(1)))


@pytest.mark.parametrize("value", [True, False], ids=["true", "false"])
def test_valid_boolean_literals(value):
    validate_expression(BoolLiteral(value))


@pytest.mark.parametrize("value", [0, 1, "True", None], ids=["zero", "one", "string", "none"])
def test_boolean_literal_requires_exact_bool_type(value):
    with pytest.raises(ASTValidationError, match="requires a bool"):
        validate_expression(BoolLiteral(value))


@pytest.mark.parametrize("name", ["x", "xA_2", "main", "ifx", "true", "false"])
def test_valid_identifiers(name):
    validate_expression(Var(name))


@pytest.mark.parametrize(
    "name",
    [
        pytest.param("if", id="reserved-if"),
        pytest.param("then", id="reserved-then"),
        pytest.param("else", id="reserved-else"),
        pytest.param("let", id="reserved-let"),
        pytest.param("in", id="reserved-in"),
        pytest.param("True", id="reserved-true"),
        pytest.param("False", id="reserved-false"),
        pytest.param("", id="empty"),
        pytest.param("X", id="uppercase-start"),
        pytest.param("_x", id="underscore-start"),
        pytest.param("1x", id="digit-start"),
        pytest.param("x-y", id="punctuation"),
        pytest.param("x y", id="space"),
        pytest.param("x\n", id="trailing-newline"),
        pytest.param("é", id="non-ascii-start"),
        pytest.param("xé", id="non-ascii-suffix"),
        pytest.param(None, id="none"),
        pytest.param(42, id="integer"),
        pytest.param(True, id="boolean"),
        pytest.param([], id="list"),
    ],
)
def test_invalid_identifiers(name):
    with pytest.raises(ASTValidationError, match="Invalid identifier"):
        validate_expression(Var(name))


@pytest.mark.parametrize(
    "tree",
    [
        pytest.param(LambdaExpr(("if",), IntLiteral(0)), id="lambda-parameter"),
        pytest.param(
            LetExpr((LocalBinding("if", (), IntLiteral(0)),), IntLiteral(0)),
            id="local-name",
        ),
        pytest.param(
            LetExpr((LocalBinding("f", ("if",), IntLiteral(0)),), IntLiteral(0)),
            id="local-parameter",
        ),
        pytest.param(Program((ValueDefinition("if", IntLiteral(0)),)), id="value-name"),
        pytest.param(
            Program((FunctionEquation("if", (VarPattern("x"),), IntLiteral(0)),)),
            id="function-name",
        ),
        pytest.param(_equation_program((VarPattern("if"),)), id="variable-pattern"),
        pytest.param(
            _equation_program((ConsPattern(VarPattern("if"), VarPattern("xs")),)),
            id="cons-head",
        ),
        pytest.param(
            _equation_program((ConsPattern(VarPattern("x"), VarPattern("if")),)),
            id="cons-tail",
        ),
    ],
)
def test_identifiers_are_checked_at_every_binding_site(tree):
    with pytest.raises(ASTValidationError, match="Invalid identifier"):
        _validate(tree)


@pytest.mark.parametrize("operator", ["+", "-", "*", "<", "<=", ">", ">=", "==", "!=", ":"])
def test_supported_binary_operators(operator):
    right = ListLiteral(()) if operator == ":" else IntLiteral(2)
    validate_expression(BinaryOp(operator, IntLiteral(1), right))


@pytest.mark.parametrize(
    "operator",
    [
        pytest.param("/", id="division"),
        pytest.param("&&", id="logical-and"),
        pytest.param("||", id="logical-or"),
        pytest.param("???", id="unknown"),
        pytest.param("", id="empty"),
        pytest.param(None, id="none"),
        pytest.param(1, id="integer"),
        pytest.param([], id="unhashable"),
    ],
)
def test_unsupported_binary_operators(operator):
    with pytest.raises(ASTValidationError, match="Unsupported binary"):
        validate_expression(BinaryOp(operator, IntLiteral(1), IntLiteral(2)))


@pytest.mark.parametrize(
    "operator", ["+", "not", "", None, 1, []],
    ids=["plus", "not", "empty", "none", "integer", "list"],
)
def test_unsupported_unary_operators(operator):
    with pytest.raises(ASTValidationError, match="Unsupported unary"):
        validate_expression(UnaryOp(operator, IntLiteral(1)))


@pytest.mark.parametrize(
    "build",
    [
        pytest.param(lambda items: Program(items), id="definitions"),
        pytest.param(lambda items: LambdaExpr(items, IntLiteral(0)), id="lambda-parameters"),
        pytest.param(lambda items: LetExpr(items, IntLiteral(0)), id="let-bindings"),
        pytest.param(lambda items: ListLiteral(items), id="list-elements"),
        pytest.param(
            lambda items: LetExpr((LocalBinding("f", items, IntLiteral(0)),), Var("f")),
            id="local-parameters",
        ),
        pytest.param(_equation_program, id="equation-parameters"),
    ],
)
@pytest.mark.parametrize("items", [[], None, "x"], ids=["list", "none", "string"])
def test_containers_must_be_tuples(build, items):
    with pytest.raises(ASTValidationError, match="tuple"):
        _validate(build(items))


@pytest.mark.parametrize(
    "tree,message",
    [
        pytest.param(LambdaExpr((), IntLiteral(0)), "at least one", id="empty-lambda"),
        pytest.param(
            LambdaExpr(("x", "x"), Var("x")),
            "Duplicate parameter", id="lambda-duplicates",
        ),
        pytest.param(LetExpr((), IntLiteral(0)), "at least one", id="empty-let"),
        pytest.param(
            LetExpr((LocalBinding("f", ("x", "x"), Var("x")),), Var("f")),
            "Duplicate parameter", id="local-parameter-duplicates",
        ),
        pytest.param(
            LetExpr(
                (LocalBinding("x", (), IntLiteral(1)), LocalBinding("x", (), IntLiteral(2))),
                Var("x"),
            ),
            "Duplicate local binding", id="duplicate-bindings",
        ),
        pytest.param(_equation_program(()), "at least one parameter", id="empty-equation"),
    ],
)
def test_invalid_binding_structure(tree, message):
    with pytest.raises(ASTValidationError, match=message):
        _validate(tree)


_EXPRESSION_CHILD_POSITIONS = [
    pytest.param(lambda child: UnaryOp("-", child), id="unary-operand"),
    pytest.param(lambda child: BinaryOp("+", child, IntLiteral(1)), id="binary-left"),
    pytest.param(lambda child: BinaryOp("+", IntLiteral(1), child), id="binary-right"),
    pytest.param(lambda child: Application(child, IntLiteral(1)), id="application-function"),
    pytest.param(lambda child: Application(Var("f"), child), id="application-argument"),
    pytest.param(lambda child: LambdaExpr(("x",), child), id="lambda-body"),
    pytest.param(lambda child: IfExpr(child, IntLiteral(1), IntLiteral(2)), id="if-condition"),
    pytest.param(lambda child: IfExpr(BoolLiteral(True), child, IntLiteral(2)), id="if-then"),
    pytest.param(lambda child: IfExpr(BoolLiteral(True), IntLiteral(1), child), id="if-else"),
    pytest.param(
        lambda child: LetExpr((LocalBinding("x", (), child),), Var("x")),
        id="local-rhs",
    ),
    pytest.param(
        lambda child: LetExpr((LocalBinding("x", (), IntLiteral(1)),), child),
        id="let-body",
    ),
    pytest.param(lambda child: ListLiteral((child, IntLiteral(1))), id="first-list-element"),
    pytest.param(lambda child: ListLiteral((IntLiteral(1), child)), id="last-list-element"),
    pytest.param(lambda child: Program((ValueDefinition("x", child),)), id="value-rhs"),
    pytest.param(
        lambda child: Program((FunctionEquation("f", (VarPattern("x"),), child),)),
        id="equation-rhs",
    ),
]


@pytest.mark.parametrize("build", _EXPRESSION_CHILD_POSITIONS)
@pytest.mark.parametrize(
    "child,message",
    [
        pytest.param(None, "Expected an Expr", id="missing-child"),
        pytest.param(VarPattern("x"), "Expected an Expr", id="wrong-node-category"),
        pytest.param(IntLiteral(True), "requires an int", id="invalid-nested-expression"),
    ],
)
def test_every_expression_child_is_validated(build, child, message):
    with pytest.raises(ASTValidationError, match=message):
        _validate(build(child))


@pytest.mark.parametrize("child", [None, IntLiteral(1)], ids=["none", "expression"])
def test_program_children_must_be_definitions(child):
    with pytest.raises(ASTValidationError, match="Expected a Definition"):
        validate_program(Program((child,)))


@pytest.mark.parametrize(
    "child", [None, ValueDefinition("x", IntLiteral(1))], ids=["none", "global-definition"]
)
def test_let_children_must_be_local_bindings(child):
    with pytest.raises(ASTValidationError, match="Expected a LocalBinding"):
        validate_expression(LetExpr((child,), IntLiteral(0)))


@pytest.mark.parametrize(
    "expression", [None, 42, Node(), Program(())], ids=["none", "integer", "node", "program"]
)
def test_expression_entry_point_rejects_wrong_categories(expression):
    with pytest.raises(ASTValidationError, match="Expected an Expr"):
        validate_expression(expression)


@pytest.mark.parametrize(
    "program", [None, 42, Node(), IntLiteral(1)], ids=["none", "integer", "node", "expression"]
)
def test_program_entry_point_rejects_wrong_categories(program):
    with pytest.raises(ASTValidationError, match="Expected a Program"):
        validate_program(program)


@pytest.mark.parametrize(
    "tree,message",
    [
        pytest.param(Expr(), "Unsupported Expr", id="abstract-expression"),
        pytest.param(Program((Definition(),)), "Unsupported Definition", id="abstract-definition"),
        pytest.param(_equation_program((Pattern(),)), "Unsupported Pattern", id="abstract-pattern"),
        pytest.param(
            _equation_program((IntLiteral(1),)), "Expected a Pattern", id="expression-pattern"
        ),
        pytest.param(_equation_program((None,)), "Expected a Pattern", id="missing-pattern"),
    ],
)
def test_unsupported_node_types(tree, message):
    with pytest.raises(ASTValidationError, match=message):
        _validate(tree)


@pytest.mark.parametrize(
    "parameters,message",
    [
        pytest.param((NilPattern(), VarPattern("y")), "final parameter", id="nil-position"),
        pytest.param(
            (ConsPattern(VarPattern("x"), VarPattern("xs")), VarPattern("y")),
            "final parameter", id="cons-position",
        ),
        pytest.param(
            (ConsPattern(VarPattern("x"), VarPattern("x")),),
            "Duplicate binder", id="cons-duplicate",
        ),
        pytest.param(
            (VarPattern("x"), VarPattern("x")),
            "Duplicate parameter binder", id="variable-duplicate",
        ),
        pytest.param(
            (VarPattern("x"), ConsPattern(VarPattern("x"), VarPattern("xs"))),
            "Duplicate parameter binder", id="cons-head-duplicate",
        ),
        pytest.param(
            (VarPattern("xs"), ConsPattern(VarPattern("x"), VarPattern("xs"))),
            "Duplicate parameter binder", id="cons-tail-duplicate",
        ),
        pytest.param(
            (ConsPattern(NilPattern(), VarPattern("xs")),),
            "two VarPattern children", id="nil-head",
        ),
        pytest.param(
            (ConsPattern(VarPattern("x"), NilPattern()),),
            "two VarPattern children", id="nil-tail",
        ),
        pytest.param(
            (ConsPattern(ConsPattern(VarPattern("x"), VarPattern("xs")), VarPattern("ys")),),
            "two VarPattern children", id="nested-head",
        ),
        pytest.param(
            (ConsPattern(VarPattern("x"), ConsPattern(VarPattern("y"), VarPattern("ys"))),),
            "two VarPattern children", id="nested-tail",
        ),
        pytest.param(
            (ConsPattern(None, VarPattern("xs")),),
            "two VarPattern children", id="missing-head",
        ),
        pytest.param(
            (ConsPattern(VarPattern("x"), Var("xs")),),
            "two VarPattern children", id="expression-tail",
        ),
    ],
)
def test_invalid_patterns(parameters, message):
    with pytest.raises(ASTValidationError, match=message):
        validate_program(_equation_program(parameters))


_VALUE_F = ValueDefinition("f", IntLiteral(1))
_EQUATION_F = FunctionEquation("f", (VarPattern("x"),), Var("x"))
_EQUATION_F_TWO_ARGS = FunctionEquation("f", (VarPattern("x"), VarPattern("y")), Var("x"))
_VALUE_G = ValueDefinition("g", IntLiteral(2))


@pytest.mark.parametrize(
    "definitions,message",
    [
        pytest.param((_VALUE_F, _VALUE_F), "Duplicate top-level", id="duplicate-values"),
        pytest.param((_VALUE_F, _EQUATION_F), "Duplicate top-level", id="value-then-function"),
        pytest.param((_EQUATION_F, _VALUE_F), "Duplicate top-level", id="function-then-value"),
        pytest.param(
            (_EQUATION_F, _EQUATION_F_TWO_ARGS), "Inconsistent arity", id="arity-increase"
        ),
        pytest.param(
            (_EQUATION_F_TWO_ARGS, _EQUATION_F), "Inconsistent arity", id="arity-decrease"
        ),
        pytest.param(
            (_EQUATION_F, _EQUATION_F, _EQUATION_F_TWO_ARGS),
            "Inconsistent arity", id="third-equation-arity",
        ),
        pytest.param((_VALUE_F, _VALUE_G, _VALUE_F), "Non-consecutive", id="separated-values"),
        pytest.param(
            (_EQUATION_F, _VALUE_G, _EQUATION_F), "Non-consecutive", id="separated-functions"
        ),
        pytest.param(
            (_VALUE_F, _VALUE_G, _EQUATION_F), "Non-consecutive", id="separated-value-function"
        ),
        pytest.param(
            (_EQUATION_F, _VALUE_G, _VALUE_F), "Non-consecutive", id="separated-function-value"
        ),
    ],
)
def test_invalid_top_level_groups(definitions, message):
    with pytest.raises(ASTValidationError, match=message):
        validate_program(Program(definitions))


@pytest.mark.parametrize(
    "span",
    [
        pytest.param(SourceSpan(1, 1, 1, 2), id="one-character-exclusive-end"),
        pytest.param(SourceSpan(1, 10, 2, 1), id="multiline-smaller-end-column"),
        pytest.param(None, id="unlocated-node"),
    ],
)
def test_valid_source_spans(span):
    validate_expression(IntLiteral(1, span=span))


@pytest.mark.parametrize("span", ["1:1", (1, 1, 1, 2), 42], ids=["string", "tuple", "integer"])
def test_source_span_requires_source_span_type(span):
    with pytest.raises(ASTValidationError, match="Invalid SourceSpan"):
        validate_expression(IntLiteral(1, span=span))


@pytest.mark.parametrize(
    "coordinate", ["start_line", "start_column", "end_line", "end_column"]
)
@pytest.mark.parametrize(
    "value", [0, -1, True, False, 1.5, "1", None],
    ids=["zero", "negative", "true", "false", "float", "string", "none"],
)
def test_source_span_positions_require_positive_exact_ints(coordinate, value):
    span = replace(SourceSpan(1, 1, 2, 2), **{coordinate: value})
    with pytest.raises(ASTValidationError, match="positive integers"):
        validate_expression(IntLiteral(1, span=span))


@pytest.mark.parametrize(
    "span",
    [
        pytest.param(SourceSpan(3, 1, 2, 10), id="reversed-lines"),
        pytest.param(SourceSpan(1, 3, 1, 2), id="reversed-columns"),
    ],
)
def test_source_span_cannot_end_before_start(span):
    with pytest.raises(ASTValidationError, match="ends before"):
        validate_expression(IntLiteral(1, span=span))


_EMPTY_SPAN = SourceSpan(1, 1, 1, 1)


@pytest.mark.parametrize(
    "tree",
    [
        pytest.param(Program((_VALUE_F,), span=_EMPTY_SPAN), id="nonempty-program"),
        pytest.param(IntLiteral(1, span=_EMPTY_SPAN), id="integer"),
        pytest.param(BoolLiteral(True, span=_EMPTY_SPAN), id="boolean"),
        pytest.param(Var("x", span=_EMPTY_SPAN), id="variable"),
        pytest.param(UnaryOp("-", IntLiteral(1), span=_EMPTY_SPAN), id="unary"),
        pytest.param(BinaryOp("+", IntLiteral(1), IntLiteral(2), span=_EMPTY_SPAN), id="binary"),
        pytest.param(Application(Var("f"), IntLiteral(1), span=_EMPTY_SPAN), id="application"),
        pytest.param(LambdaExpr(("x",), Var("x"), span=_EMPTY_SPAN), id="lambda"),
        pytest.param(
            IfExpr(BoolLiteral(True), IntLiteral(1), IntLiteral(2), span=_EMPTY_SPAN), id="if"
        ),
        pytest.param(
            LetExpr((LocalBinding("x", (), IntLiteral(1)),), Var("x"), span=_EMPTY_SPAN), id="let"
        ),
        pytest.param(ListLiteral((), span=_EMPTY_SPAN), id="empty-list-syntax"),
        pytest.param(
            LetExpr((LocalBinding("x", (), IntLiteral(1), span=_EMPTY_SPAN),), Var("x")),
            id="local-binding",
        ),
        pytest.param(Program((replace(_VALUE_F, span=_EMPTY_SPAN),)), id="value-definition"),
        pytest.param(Program((replace(_EQUATION_F, span=_EMPTY_SPAN),)), id="function-equation"),
        pytest.param(
            _equation_program((VarPattern("x", span=_EMPTY_SPAN),)), id="variable-pattern"
        ),
        pytest.param(_equation_program((NilPattern(span=_EMPTY_SPAN),)), id="nil-pattern"),
        pytest.param(
            _equation_program((ConsPattern(VarPattern("x"), VarPattern("xs"), span=_EMPTY_SPAN),)),
            id="cons-pattern",
        ),
    ],
)
def test_concrete_syntax_rejects_empty_spans(tree):
    with pytest.raises(ASTValidationError, match="must not be empty"):
        _validate(tree)


def test_empty_program_allows_empty_span():
    validate_program(Program((), span=_EMPTY_SPAN))


_PARENT_SPAN = SourceSpan(3, 1, 3, 30)
_CHILD_SPAN = SourceSpan(3, 10, 3, 15)


@pytest.mark.parametrize("build", _EXPRESSION_CHILD_POSITIONS)
@pytest.mark.parametrize(
    "child_span,start",
    [
        pytest.param(_CHILD_SPAN, "3:10", id="child-location"),
        pytest.param(None, "3:1", id="parent-fallback"),
    ],
)
def test_nested_expression_error_location(build, child_span, start):
    tree = replace(build(Var("if", span=child_span)), span=_PARENT_SPAN)
    with pytest.raises(ASTValidationError, match=rf"^{start}: Invalid identifier"):
        _validate(tree)


def test_nearest_enclosing_span_is_used():
    expr = LetExpr(
        (
            LocalBinding(
                "x",
                (),
                Application(Var("f"), Var("if")),
                span=_CHILD_SPAN,
            ),
        ),
        Var("x"),
        span=_PARENT_SPAN,
    )
    with pytest.raises(ASTValidationError, match=r"^3:10: Invalid identifier"):
        validate_expression(expr)


@pytest.mark.parametrize(
    "tree,message",
    [
        pytest.param(
            ListLiteral((NilPattern(span=_CHILD_SPAN),), span=_PARENT_SPAN),
            "Expected an Expr", id="wrong-expression-category",
        ),
        pytest.param(
            LetExpr((Var("x", span=_CHILD_SPAN),), IntLiteral(0), span=_PARENT_SPAN),
            "Expected a LocalBinding", id="wrong-binding-category",
        ),
        pytest.param(
            Program((IntLiteral(1, span=_CHILD_SPAN),), span=_PARENT_SPAN),
            "Expected a Definition", id="wrong-definition-category",
        ),
        pytest.param(
            replace(_equation_program((IntLiteral(1, span=_CHILD_SPAN),)), span=_PARENT_SPAN),
            "Expected a Pattern", id="wrong-pattern-category",
        ),
        pytest.param(
            replace(
                _equation_program((ConsPattern(VarPattern("x"), NilPattern(span=_CHILD_SPAN)),)),
                span=_PARENT_SPAN,
            ),
            "two VarPattern children", id="wrong-cons-child",
        ),
        pytest.param(
            replace(
                _equation_program((NilPattern(span=_CHILD_SPAN), VarPattern("x"))),
                span=_PARENT_SPAN,
            ),
            "final parameter", id="pattern-position",
        ),
        pytest.param(
            replace(
                _equation_program(
                    (ConsPattern(VarPattern("x"), VarPattern("x", span=_CHILD_SPAN)),)
                ),
                span=_PARENT_SPAN,
            ),
            "Duplicate binder", id="duplicate-cons-binder",
        ),
        pytest.param(
            replace(
                _equation_program(
                    (
                        VarPattern("x"),
                        ConsPattern(VarPattern("x", span=_CHILD_SPAN), VarPattern("xs")),
                    )
                ),
                span=_PARENT_SPAN,
            ),
            "Duplicate parameter binder", id="duplicate-equation-binder",
        ),
        pytest.param(
            LetExpr(
                (LocalBinding("if", (), IntLiteral(0), span=_CHILD_SPAN),),
                IntLiteral(0),
                span=_PARENT_SPAN,
            ),
            "Invalid identifier", id="invalid-local-name",
        ),
        pytest.param(
            Program(
                (_VALUE_F, replace(_VALUE_F, span=_CHILD_SPAN)),
                span=_PARENT_SPAN,
            ),
            "Duplicate top-level", id="duplicate-definition",
        ),
    ],
)
def test_offending_child_location_is_prioritized(tree, message):
    with pytest.raises(ASTValidationError, match=message) as error:
        _validate(tree)
    assert str(error.value).startswith("3:10: ")


@pytest.mark.parametrize(
    "tree,message",
    [
        pytest.param(
            ListLiteral((None,), span=_PARENT_SPAN), "Expected an Expr", id="missing-expression"
        ),
        pytest.param(
            LetExpr((None,), IntLiteral(0), span=_PARENT_SPAN),
            "Expected a LocalBinding", id="missing-binding",
        ),
        pytest.param(
            Program((None,), span=_PARENT_SPAN), "Expected a Definition", id="missing-definition"
        ),
        pytest.param(
            replace(_equation_program((None,)), span=_PARENT_SPAN),
            "Expected a Pattern", id="missing-pattern",
        ),
        pytest.param(
            replace(_equation_program((ConsPattern(VarPattern("x"), None),)), span=_PARENT_SPAN),
            "two VarPattern children", id="missing-cons-child",
        ),
        pytest.param(
            ListLiteral((Var("x", span="bad"),), span=_PARENT_SPAN),
            "Invalid SourceSpan", id="invalid-child-span-type",
        ),
        pytest.param(
            Program((_VALUE_F, _VALUE_F), span=_PARENT_SPAN),
            "Duplicate top-level", id="unlocated-duplicate-definition",
        ),
        pytest.param(
            replace(_equation_program((NilPattern(), VarPattern("x"))), span=_PARENT_SPAN),
            "final parameter", id="unlocated-pattern-position",
        ),
        pytest.param(
            replace(
                _equation_program((ConsPattern(VarPattern("x"), VarPattern("x")),)),
                span=_PARENT_SPAN,
            ),
            "Duplicate binder", id="unlocated-duplicate-cons-binder",
        ),
    ],
)
def test_parent_location_is_used_when_child_has_no_span(tree, message):
    with pytest.raises(ASTValidationError, match=message) as error:
        _validate(tree)
    assert str(error.value).startswith("3:1: ")


def test_invalid_node_without_any_span_has_unlocated_error():
    with pytest.raises(ASTValidationError) as error:
        validate_expression(Var("if"))
    assert str(error.value) == "Invalid identifier: 'if'"


def test_source_span_error_location():
    expr = BinaryOp("?", IntLiteral(1), IntLiteral(2), span=_CHILD_SPAN)
    with pytest.raises(ASTValidationError, match=r"^3:10: Unsupported binary"):
        validate_expression(expr)

def test_main_as_function_equation_error():
    program = Program((
        FunctionEquation("main", (VarPattern("x"),), Var("x")),
    ))

    with pytest.raises(ASTValidationError, match=r"\bmain\b"):
        validate_program(program)

def test_main_as_value_definition_is_valid():
    program = Program((
        ValueDefinition("main", IntLiteral(42)),
    ))
    validate_program(program)

def test_deep_left_associative_ast_validation():
    source = " + ".join(["1"] * 2000)

    expression = parse_expression(source)

    validate_expression(expression)

_DEEP_WRAPPERS = [
    pytest.param(lambda child: Application(child, IntLiteral(1)), id="application"),
    pytest.param(lambda child: BinaryOp("+", child, IntLiteral(1)), id="binary"),
    pytest.param(lambda child: UnaryOp("-", child), id="unary"),
    pytest.param(lambda child: LambdaExpr(("x",), child), id="lambda"),
    pytest.param(lambda child: IfExpr(BoolLiteral(True), child, IntLiteral(0)), id="if"),
    pytest.param(lambda child: ListLiteral((child,)), id="list"),
    pytest.param(
        lambda child: LetExpr((LocalBinding("x", (), child),), Var("x")),
        id="let-rhs",
    ),
    pytest.param(
        lambda child: LetExpr((LocalBinding("x", (), IntLiteral(0)),), child),
        id="let-body",
    ),
]


def _nest(build, leaf):
    for _ in range(2000):
        leaf = build(leaf)
    return leaf


@pytest.mark.parametrize("build", _DEEP_WRAPPERS)
def test_deep_constructed_expression_and_program(build):
    expression = _nest(build, IntLiteral(1))
    validate_expression(expression)
    validate_program(Program((
        ValueDefinition("main", expression),
        FunctionEquation("f", (VarPattern("x"),), expression),
    )))


@pytest.mark.parametrize("build", _DEEP_WRAPPERS)
@pytest.mark.parametrize("located_leaf", [False, True])
def test_deep_invalid_descendant_location(build, located_leaf):
    leaf = Var("if", span=_CHILD_SPAN if located_leaf else None)
    expression = _nest(build, leaf)
    # An inner located ancestor must take precedence over the program span.
    expression = replace(expression, span=_CHILD_SPAN)
    program = Program((ValueDefinition("main", expression),), span=_PARENT_SPAN)
    for tree in (expression, program):
        with pytest.raises(ASTValidationError, match="^3:10: Invalid identifier: 'if'$"):
            _validate(tree)


def test_local_rhs_error_precedes_later_binding_checks():
    expression = LetExpr((
        LocalBinding("x", (), Var("if", span=_CHILD_SPAN)),
        LocalBinding("x", (), IntLiteral(0)),
    ), Var("x"))
    with pytest.raises(ASTValidationError, match="^3:10: Invalid identifier"):
        validate_expression(expression)


def test_first_child_error_precedes_later_child_errors():
    expression = IfExpr(
        Var("if", span=_CHILD_SPAN),
        Var("then", span=_PARENT_SPAN),
        None,
    )
    with pytest.raises(ASTValidationError, match="^3:10: Invalid identifier: 'if'$"):
        validate_expression(expression)
