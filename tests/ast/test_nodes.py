from dataclasses import replace

import pytest

from lazy_lab.ast.nodes import (
    Application,
    BinaryOp,
    UnaryOp,
    BoolLiteral,
    IfExpr,
    IntLiteral,
    LambdaExpr,
    LetExpr,
    ListLiteral,
    LocalBinding,
    Var,
    Program,
    SourceSpan,
    ValueDefinition,
    FunctionEquation,
    VarPattern,
    NilPattern,
    ConsPattern,
)


def test_empty_program():
    program = Program(definitions=())

    assert program.definitions == ()


def test_source_span():
    span = SourceSpan(1, 1, 1, 10)

    assert span.start_line == 1
    assert span.end_column == 10


# Simple Expressions
def test_literals():
    integer = IntLiteral(value=42)
    boolean = BoolLiteral(value=True)

    assert integer.value == 42
    assert boolean.value is True


def test_variable():
    variable = Var(name="x")

    assert variable.name == "x"


def test_binary_operation():
    expression = BinaryOp(
        operator="+",
        left=IntLiteral(3),
        right=IntLiteral(2)
    )

    assert expression.operator == "+"
    assert expression.left == IntLiteral(3)
    assert expression.right == IntLiteral(2)


def test_unary_operation():
    expression = UnaryOp(
        operator="-",
        operand=IntLiteral(10)
    )

    assert expression.operand == IntLiteral(10)


def test_nested_application():
    expression = Application(
        function=Application(
            function=Var("sum"),
            argument=IntLiteral(3)
        ),
        argument=IntLiteral(4)
    )

    assert isinstance(expression.function, Application)
    assert expression.function.function == Var("sum")
    assert expression.function.argument == IntLiteral(3)
    assert expression.argument == IntLiteral(4)


def test_application_inside_binary_operation():
    expression = BinaryOp(
        operator="+",
        left=Application(
            function=Var("double"),
            argument=IntLiteral(3)
        ),
        right=IntLiteral(2)
    )

    assert isinstance(expression.left, Application)
    assert expression.operator == "+"
    assert expression.right == IntLiteral(2)

# Complex Expressions

def test_lambda():
    expr = LambdaExpr(
        parameters=("x", "y"),
        body=BinaryOp("+", Var("x"), Var("y"))
    )

    assert expr.parameters == ("x", "y")
    assert isinstance(expr.body, BinaryOp)


def test_if_expression():
    expr = IfExpr(
        condition=BoolLiteral(True),
        then_branch=IntLiteral(10),
        else_branch=IntLiteral(20)
    )

    assert expr.condition == BoolLiteral(True)
    assert expr.then_branch == IntLiteral(10)


def test_local_bindings():
    expr = LetExpr(
        bindings=(
            LocalBinding(
                name="x",
                parameters=(),
                rhs=IntLiteral(10)
            ),
            LocalBinding(
                name="y",
                parameters=(),
                rhs=Var("x")
            )
        ),
        body=Var("y")
    )

    assert len(expr.bindings) == 2
    assert expr.bindings[1].rhs == Var("x")
    assert expr.body == Var("y")


def test_list_literal():
    expr = ListLiteral(
        elements=(IntLiteral(1), IntLiteral(2))
    )

    assert len(expr.elements) == 2
    assert expr.elements[0] == IntLiteral(1)


def test_empty_list():
    expr = ListLiteral(elements=())

    assert expr.elements == ()


def test_cons_expression():
    expr = BinaryOp(
        operator=":",
        left=IntLiteral(1),
        right=ListLiteral(elements=())
    )

    assert expr.operator == ":"
    assert isinstance(expr.right, ListLiteral)


def test_local_function():
    binding = LocalBinding(
        name="double",
        parameters=("x",),
        rhs=BinaryOp("*", Var("x"), IntLiteral(2))
    )

    assert binding.name == "double"
    assert binding.parameters == ("x",)
    assert isinstance(binding.rhs, BinaryOp)

def test_variable_pattern():
    pattern = VarPattern("x")

    assert pattern.name == "x"


def test_nil_pattern():
    pattern = NilPattern()

    assert isinstance(pattern, NilPattern)


def test_cons_pattern():
    pattern = ConsPattern(
        head=VarPattern("x"),
        tail=VarPattern("xs")
    )

    assert pattern.head.name == "x"
    assert pattern.tail.name == "xs"


def test_value_definition():
    definition = ValueDefinition(
        name="answer",
        rhs=IntLiteral(42)
    )

    assert definition.name == "answer"
    assert definition.rhs == IntLiteral(42)


def test_function_equation():
    equation = FunctionEquation(
        name="double",
        parameters=(VarPattern("x"),),
        rhs=BinaryOp(
            "*",
            Var("x"),
            IntLiteral(2)
        )
    )

    assert equation.name == "double"
    assert len(equation.parameters) == 1
    assert equation.parameters[0] == VarPattern("x")


def test_multiple_equations():
    program = Program(
        definitions=(
            FunctionEquation(
                name="length",
                parameters=(NilPattern(),),
                rhs=IntLiteral(0)
            ),
            FunctionEquation(
                name="length",
                parameters=(
                    ConsPattern(
                        VarPattern("x"),
                        VarPattern("xs")
                    ),
                ),
                rhs=IntLiteral(1)
            )
        )
    )

    assert len(program.definitions) == 2
    assert all(
        isinstance(d, FunctionEquation)
        for d in program.definitions
    )
    assert program.definitions[0].name == "length"
    assert program.definitions[1].name == "length"


@pytest.mark.parametrize(
    "node",
    [
        pytest.param(Program((ValueDefinition("x", IntLiteral(1)),)), id="program"),
        pytest.param(IntLiteral(1), id="integer"),
        pytest.param(BoolLiteral(True), id="boolean"),
        pytest.param(Var("x"), id="variable"),
        pytest.param(UnaryOp("-", IntLiteral(1)), id="unary"),
        pytest.param(BinaryOp("+", IntLiteral(1), IntLiteral(2)), id="binary"),
        pytest.param(Application(Var("f"), IntLiteral(1)), id="application"),
        pytest.param(LambdaExpr(("x",), Var("x")), id="lambda"),
        pytest.param(IfExpr(BoolLiteral(True), IntLiteral(1), IntLiteral(2)), id="if"),
        pytest.param(LocalBinding("x", (), IntLiteral(1)), id="local-binding"),
        pytest.param(LetExpr((LocalBinding("x", (), IntLiteral(1)),), Var("x")), id="let"),
        pytest.param(ListLiteral((IntLiteral(1),)), id="list"),
        pytest.param(VarPattern("x"), id="variable-pattern"),
        pytest.param(NilPattern(), id="nil-pattern"),
        pytest.param(ConsPattern(VarPattern("x"), VarPattern("xs")), id="cons-pattern"),
        pytest.param(ValueDefinition("x", IntLiteral(1)), id="value-definition"),
        pytest.param(FunctionEquation("f", (VarPattern("x"),), Var("x")), id="function-equation"),
    ],
)
def test_source_span_is_excluded_from_node_equality_and_hashing(node):
    first = replace(node, span=SourceSpan(1, 1, 1, 2))
    second = replace(node, span=SourceSpan(2, 3, 2, 4))

    assert node == first == second
    assert hash(node) == hash(first) == hash(second)


def test_nested_node_equality_ignores_all_source_spans():
    def make_program(span):
        return Program(
            (
                FunctionEquation(
                    "f",
                    (
                        ConsPattern(
                            VarPattern("x", span=span),
                            VarPattern("xs", span=span),
                            span=span,
                        ),
                    ),
                    LetExpr(
                        (LocalBinding("y", (), Var("x", span=span), span=span),),
                        Var("y", span=span),
                        span=span,
                    ),
                    span=span,
                ),
            ),
            span=span,
        )

    unlocated = make_program(None)
    first = make_program(SourceSpan(1, 1, 1, 30))
    second = make_program(SourceSpan(2, 1, 2, 40))

    assert unlocated == first == second
    assert hash(unlocated) == hash(first) == hash(second)


@pytest.mark.parametrize(
    "left,right",
    [
        pytest.param(IntLiteral(1), IntLiteral(2), id="literal-value"),
        pytest.param(IntLiteral(1), BoolLiteral(True), id="node-type"),
        pytest.param(Var("x"), Var("y"), id="name"),
        pytest.param(
            BinaryOp("+", IntLiteral(1), IntLiteral(2)),
            BinaryOp("-", IntLiteral(1), IntLiteral(2)),
            id="operator",
        ),
        pytest.param(
            LambdaExpr(("x", "y"), Var("x")),
            LambdaExpr(("y", "x"), Var("x")),
            id="parameter-order",
        ),
        pytest.param(
            ListLiteral((IntLiteral(1), IntLiteral(2))),
            ListLiteral((IntLiteral(2), IntLiteral(1))),
            id="child-order",
        ),
        pytest.param(
            Program(
                (
                    FunctionEquation("f", (VarPattern("x"),), IntLiteral(0)),
                    FunctionEquation("f", (NilPattern(),), IntLiteral(1)),
                )
            ),
            Program(
                (
                    FunctionEquation("f", (NilPattern(),), IntLiteral(1)),
                    FunctionEquation("f", (VarPattern("x"),), IntLiteral(0)),
                )
            ),
            id="equation-order",
        ),
    ],
)
def test_structural_differences_still_affect_equality(left, right):
    assert left != right


def test_source_span_values_still_compare_by_position():
    assert SourceSpan(1, 1, 1, 2) == SourceSpan(1, 1, 1, 2)
    assert SourceSpan(1, 1, 1, 2) != SourceSpan(2, 1, 2, 2)
