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
    BoolLiteral,
    IntLiteral,
    UnaryOp,
    Var,
)


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