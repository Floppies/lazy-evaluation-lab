from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SourceSpan:
    start_line: int
    start_column: int
    end_line: int
    end_column: int