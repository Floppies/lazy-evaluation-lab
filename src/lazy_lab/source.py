from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SourceSpan:
    """One-based range with an inclusive start and exclusive end.

    Columns count source characters, including one column per horizontal tab.
    EOF tokens and empty programs may use a zero-width range; structural AST
    validation rejects empty ranges on concrete syntax nodes.
    """

    start_line: int
    start_column: int
    end_line: int
    end_column: int
