from .tokens import Token

class LexerError(ValueError):
    def __init__(self, message: str, line: int, column: int):
        self.line = line
        self.column = column
        super().__init__(f"{line}:{column}: {message}")

class ParserError(ValueError):
    def __init__(self, message: str, token: "Token"):
        self.line = token.span.start_line
        self.column = token.span.start_column
        self.token = token

        super().__init__(
            f"{self.line}:{self.column}: {message}"
        )