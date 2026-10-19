
# Frontend — Lazy Evaluation Lab

## Overview

The frontend transforms source code written in the mini-language into an Abstract Syntax Tree (AST).

The pipeline consists of three independent stages:

1. Lexical analysis (`tokenize`)
2. Syntax analysis (`parse_program` / `parse_expression`)
3. Structural validation (`validate_program` / `validate_expression`)

The frontend does not evaluate programs, resolve variable references, or perform runtime type checking.

## Public API

```python
from lazy_lab.frontend.lexer import tokenize
from lazy_lab.frontend.parser import parse_program, parse_expression
from lazy_lab.ast.validation import validate_program, validate_expression
```

### Tokenization

`tokenize(source: str) -> tuple[Token, ...]`

Returns an immutable sequence of tokens ending in EOF. Tokens preserve lexemes and source locations.

### Program parsing

`parse_program(source: str) -> Program`

Parses a source file consisting of top-level definitions. A `main` binding is optional.

### Expression parsing

`parse_expression(source: str) -> Expr`

Parses one standalone expression. This entry point supports the laboratory's user-selected evaluation expressions.

### Structural validation

`validate_program(program: Program) -> None`

`validate_expression(expression: Expr) -> None`

Validation is explicit and separate from parsing. It checks AST structure, supported operators, identifiers, binding restrictions, and function equation groups.

Both validators traverse expressions with an explicit depth-first stack. Already constructed ASTs, including long left-associative chains and deeply nested local bindings, are validated without depending on Python recursion depth or imposing an AST-depth limit. The parser's 64-context nesting limit applies to recursive syntax parsing only; long left-associative addition chains do not consume those nesting contexts.

## Error Handling

- `LexerError`: invalid lexical input.
- `ParserError`: invalid syntax or excessive parser nesting.
- `ASTValidationError`: structurally invalid AST.

Errors preserve source locations when available.

## Source Locations

Source spans use one-based coordinates, an inclusive start, and an exclusive end.

Source locations do not participate in AST structural equality. They do participate in Token equality.

## Current Limitations

- One physical line per top-level definition.
- No indentation-sensitive layout.
- No static type checking.
- No name resolution at this stage.
- Limited constructor patterns.
- Recursive parsing depth is bounded (64 nesting contexts in v0.1).

See `language-specification.md` for the full grammar and semantic decisions.
