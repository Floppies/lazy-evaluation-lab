# Lazy Evaluation Lab

An experimental laboratory for studying and visualizing evaluation strategies in functional programming languages.

This project is being developed as a Computer Engineering thesis.

## Objectives

The project aims to:

- Implement a small functional language with Haskell-inspired syntax.
- Compare Call-by-Value (CBV), Call-by-Name (CBN), and Call-by-Need (CBNeed) evaluation strategies.
- Visualize program execution, including memory allocation, environments, closures, and thunks.
- Collect execution metrics to analyze memory usage, computation sharing, and evaluation behavior.

## Architecture

The language processing pipeline is organized as follows:

```text
Source Code
    ↓
Lexer / Parser
    ↓
   AST
    ↓
Desugaring
    ↓
Core IR
    ↓
Evaluation Runtime (CBV / CBN / CBNeed)
    ↓
Execution State, Metrics and Visualization
```

The implementation is written primarily in Python.

## Project Structure

- `src/lazy_lab/frontend/` — Lexical and syntactic analysis.
- `src/lazy_lab/ast/` — Abstract Syntax Tree and validation.
- `src/lazy_lab/core/` — Core intermediate representation and desugaring.
- `tests/` — Automated tests.
- `examples/` — Sample programs written in the mini-language.
- `docs/` — Technical documentation and design decisions.

## Development Setup

Requires Python 3.11 or newer.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

Run tests using:

```bash
python -m pytest
```

## Status

Early development. The current focus is implementing the language frontend and Core intermediate representation.