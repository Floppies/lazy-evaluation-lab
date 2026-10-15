from lazy_lab.ast.nodes import Program, SourceSpan

def test_empty_program():
    program = Program(definitions=())

    assert program.definitions == ()


def test_source_span():
    span = SourceSpan(1, 1, 1, 10)

    assert span.start_line == 1
    assert span.end_column == 10

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
)

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