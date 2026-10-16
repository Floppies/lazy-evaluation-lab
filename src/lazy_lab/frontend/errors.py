class LexerError(ValueError):
    def __init__(self, message: str, line: int, column: int):
        self.line = line
        self.column = column
        super().__init__(f"{line}:{column}: {message}")