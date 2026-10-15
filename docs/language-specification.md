# Lazy Evaluation Lab — Mini-Language Specification

**Version:** 0.1 (B02.2 baseline)  
**Status:** B02.2 reviewed baseline, revised for consistency before implementation of the lexer, parser, AST and Core lowering.  
**Scope:** Initial mini-language only; planned extensions are recorded in Section 10.

## 1. Program Structure

### 1.1 Top-Level Definitions

- A program consists of top-level definitions.
- Each definition occupies a single line.
- Definitions are separated by newlines.
- A definition has the form:
  `name parameter1 ... parameterN = expression`
- Parameters are optional.
- Top-level recursion and mutual recursion are allowed.
- Modules, imports, and type declarations are not supported.

### 1.2 Program Entry Point

The program may optionally define `main` as an ordinary top-level binding. When the user executes the program without selecting a different expression, `main` is used as the default entry point. Parsing, validation, and Core generation do not require `main`; execution without `main` requires an explicitly selected expression. The entry point does not itself print or fully force its result (see Sections 8.5 and 9).

## 2. Literals and Identifiers

### 2.1 Literals
- Integer literals: non-negative decimal integers represented with arbitrary precision (Python `int` in the initial implementation).
- Boolean literals: `True` and `False`.
- Negative values are expressed using unary negation.

### 2.2 Identifiers
- Identifiers must match `[a-z][a-zA-Z0-9_]*`.
- Identifiers are case-sensitive.
- Reserved words cannot be used as identifiers.

### 2.3 Reserved Words
`if`, `then`, `else`, `let`, `in`, `True`, `False`.

## 3. Expressions and Operators

### 3.1 Expressions
Expressions include:
- Integer and boolean literals.
- Variable references.
- Function applications.
- Unary and binary operations.
- Parenthesized expressions.
- Lambda expressions.
- Conditional expressions (`if ... then ... else ...`).
- Local bindings (`let { ... } in ...`).
- List literals (`[ ... ]`) and list construction with `:`.

### 3.2 Function Application
- Function application uses whitespace.
- Application is left-associative.
- Application has higher precedence than arithmetic operators.

### 3.3 Operators
- Arithmetic: +, -, *
- Comparison: <, <=, >, >=
- Equality: ==, !=
- Unary negation: -
- List construction (cons): :

### 3.4 Precedence
From highest to lowest:
1. Parenthesized expressions
2. Function application
3. Unary negation
4. Multiplication
5. Addition and subtraction
6. List construction (`:`)
7. Comparison and equality

Arithmetic operators are left-associative. List construction is right-associative. Comparison and equality operators are non-associative.

For example, `double 3 + 2` means `(double 3) + 2`, `1 + 2 : []` means `(1 + 2) : []`, and `1 : 2 : []` means `1 : (2 : [])`. To pass a negative literal directly to a function, write `f (-3)`; `f - 3` denotes subtraction. Parentheses may group any full expression, including `let`, `if`, and lambda expressions.

### 3.5 Limitations
Division and boolean logical operators are not supported
in the initial version.

## 4. Functions, Lambdas and Currying

### 4.1 Function Definitions

Functions are defined using the syntax:

`name parameter1 ... parameterN = expression`

Functions may have one or more parameters.
Definitions without parameters represent values.

### 4.2 Lambda Expressions

Anonymous functions use the syntax:

`\parameter -> expression`

Multiple parameters are supported:

`\x y -> expression`

The lambda body extends to the right within its
enclosing expression. Parentheses can be used
for explicit grouping.

### 4.3 Currying

All functions are represented internally as unary
functions.

A function with multiple parameters:

`f x y = expression`

is desugared into:

`f = \x -> \y -> expression`

This unary Core representation describes the semantics of a curried function. It does not require the runtime to allocate a separate intermediate closure for each argument when a call is saturated. Such an optimization is deferred; the initial runtime may follow the simpler unary application model while tracking actual allocations separately from semantic application steps.

### 4.4 Higher-Order Functions

Functions are first-class values and may be:

- Passed as arguments.
- Returned from other functions.
- Partially applied.
- Assigned to bindings.

### 4.5 Scoping

Lambda parameters introduce local bindings.
References to variables from enclosing scopes are
allowed.

Duplicate parameters within the same function
parameter list are not permitted.

## 5. Conditional Expressions

### 5.1 Syntax

Conditional expressions use the following syntax:

`if condition then expression1 else expression2`

### 5.2 Rules

- Conditionals are expressions, not statements.
- Both `then` and `else` branches are mandatory.
- The condition must evaluate to a boolean value.
- Only the selected branch is evaluated.
- Conditionals have lower precedence than arithmetic
  operators and function application.
- Parentheses are required when using a conditional
  as a function argument or within an arithmetic operation.
- Nested conditionals are supported.

### 5.3 Core Representation

Conditional expressions are preserved as `CoreIf` nodes.

`CoreIf` contains:
- A condition expression.
- A then-branch expression.
- An else-branch expression.

The runtime must evaluate the condition and select
exactly one branch, regardless of the evaluation strategy. `CoreIf` must not be desugared into an ordinary strict function application that evaluates both branches before choosing one.

### 5.4 Validation

The parser validates the presence and structure of all
three components. Since the initial language does not
include static type checking, a non-boolean condition
is rejected at runtime.

## 6. Bindings, Scope and Recursion

### 6.1 Bindings

A binding associates an identifier with an expression.

Bindings do not determine when or how their associated expressions are evaluated. Evaluation behavior depends on the selected evaluation strategy (CBV, CBN or CBNeed).

The language supports both top-level and local bindings.

### 6.2 Local Bindings

Local bindings are introduced using `let` expressions.

The syntax supports one or more bindings enclosed in braces and separated by semicolons:

```haskell
let { x = 10; y = 20 } in x + y
```

A single binding is also permitted:

```haskell
let { x = 10 } in x + x
```

Local function bindings without constructor patterns are supported:

```haskell
let { double x = x * 2; value = double 5 } in value
```

The braced form is required even for a single local binding in v0.1. Indentation-sensitive `let` syntax is deferred.

The `let` construct is an expression and may appear wherever an expression is allowed, subject to the language's grouping rules.

Local binding groups are recursive: every binding is visible in the right-hand side of every other binding in the same group, including itself.

### 6.3 Lexical Scoping

The language uses lexical scoping.

- Top-level bindings are visible throughout the program, independently of declaration order.
- Function parameters and lambda parameters introduce local bindings.
- Each `let` expression introduces a new lexical scope.
- Inner bindings may shadow identifiers from enclosing scopes.
- Duplicate binding names within the same scope are not allowed, except for consecutive equations belonging to the same function definition.
- References to undefined identifiers are rejected during semantic validation.

For example, in `x = 10` followed by `main = let { x = 5 } in x + 1`, the local `x` shadows the global `x`; the expression uses `5` rather than `10`.

### 6.4 Recursion

The language supports:

- Direct recursion.
- Mutual recursion between top-level functions.
- Direct and mutual recursion within local `let` binding groups.

For example:

```haskell
isEven n = if n == 0 then True else isOdd (n - 1)
isOdd n = if n == 0 then False else isEven (n - 1)
main = isEven 10
```

Recursive bindings may create circular dependencies:

```haskell
main = let { x = x } in x
```

Such programs are syntactically valid. Their execution behavior, including possible nontermination or blackhole detection, is determined by the runtime and evaluation strategy.

### 6.5 Core Representation

Local binding groups will be lowered to a recursive binding representation, provisionally named `CoreLetRec`.

The Core representation must preserve lexical scoping, recursion and shadowing without imposing any particular evaluation strategy.

The exact representation and execution of recursive environments will be defined during the Core and runtime design stages.

---

## 7. Lists and Pattern Matching

### 7.1 List Expressions

The language supports list literals:

```haskell
numbers = [1, 2, 3]
empty = []
```

List elements may be arbitrary expressions.

Lists may also be constructed using the cons operator (`:`):

```haskell
numbers = 1 : 2 : 3 : []
```

The cons operator is right-associative and has lower precedence than addition and multiplication but higher precedence than comparison operators.

### 7.2 List Representation

Lists are represented conceptually using two constructors:

- `Nil`: represents an empty list.
- `Cons(head, tail)`: represents a non-empty list.

List literals are syntactic sugar.

For example:

```haskell
[1, 2, 3]
```

is desugared into:

```text
Cons(1, Cons(2, Cons(3, Nil)))
```

The runtime determines when constructor fields are evaluated, according to the selected evaluation strategy. `Cons` is a data constructor, not necessarily an ordinary strict binary function. In lazy strategies, recognizing the outer `Cons` does not force its head or tail.

### 7.3 Supported Patterns

The initial language supports the following patterns in top-level function equations:

- Variable pattern: `x`
- Empty-list pattern: `[]`
- Cons pattern: `x:xs`

Cons patterns must be enclosed in parentheses when used as function parameters.

For example:

```haskell
length [] = 0
length (x:xs) = 1 + length xs
```

Only one level of constructor matching is supported. Nested patterns, guards, numeric patterns and wildcard patterns are excluded from the initial version.

### 7.4 Pattern Position Restrictions

Constructor patterns (`[]` and `x:xs`) are permitted only in the last argument of a top-level function definition.

All preceding parameters must be variable identifiers.

Valid:

```haskell
map f [] = []
map f (x:xs) = f x : map f xs
```

Not supported:

```haskell
compareLists [] ys = 0
compareLists (x:xs) ys = 1
```

Pattern matching in local `let` bindings and lambda parameters is not supported initially.

### 7.5 Multiple Function Equations

A top-level function may be defined through multiple consecutive equations.

All equations must:

- Have the same function name.
- Have the same number of parameters.
- Appear consecutively in the source file.

Patterns are matched in source order. Blank lines and comment-only lines do not interrupt a group of consecutive equations; a definition with a different name does.

A variable pattern matches any argument **without demanding its value** under CBN or CBNeed, whereas constructor patterns inspect the outermost list constructor. If a variable-pattern equation occurs first, later equations must not be tried. More generally, later equations are attempted only if preceding equations fail to match.

If no equation matches, evaluation produces a pattern-matching error.

Exhaustiveness checking is not required in the initial implementation.

### 7.6 Lazy Evaluation and Pattern Matching

Matching the constructor pattern `[]` or `(x:xs)` requires evaluating the inspected argument sufficiently to determine its outermost constructor. **A variable pattern does not require inspecting the argument** under CBN and CBNeed.

For example, in the following program, the first equation matches without forcing `loop` under CBN or CBNeed:

```haskell
f x = 10
f [] = 20
loop = loop
main = f loop
```

The same program may diverge under CBV because CBV evaluates the argument before applying `f`. This difference arises from CBV argument evaluation, not from the variable pattern itself.

Under CBN and CBNeed, matching a `Cons` constructor does not require evaluating its head or tail contents.

Under CBV, constructor fields are evaluated according to the strict evaluation rules of the runtime.

This distinction is important for studying demand, sharing, memory allocation and evaluation to Weak Head Normal Form (WHNF).

### 7.7 Core Representation

Pattern matching will be desugared into a `CoreCase` expression.

For example:

```haskell
length [] = 0
length (x:xs) = 1 + length xs
```

will be transformed conceptually into:

```haskell
length = \list -> case list of
    Nil       -> 0
    Cons x xs -> 1 + length xs
```

The `case` syntax shown above is illustrative and is not part of the initial source language.

`CoreCase` will contain:

- A scrutinee expression.
- An ordered set of alternatives.
- Pattern-bound variables and their corresponding expressions.

The Core representation must preserve pattern matching order and the runtime's strategy-dependent evaluation behavior. In particular, the lowering must **not** introduce an unconditional constructor inspection when an earlier variable pattern already matches. A variable-pattern fallback reached after failed constructor alternatives is permitted, but must preserve the evaluation already required by those earlier alternatives.

`CoreIf` will remain a separate construct for conditional expressions. Its possible replacement by a generalized `CoreCase` will be reconsidered during later development.

## 8. Formal Grammar (EBNF)

### 8.1 Expressions

The following grammar defines the supported expression syntax, including operator precedence, function application, conditional expressions, lambda expressions, local bindings and list literals. `BACKSLASH` is the lexical token corresponding to the source character `\` (defined in Section 8.6). This avoids relying on a particular EBNF implementation's string-escaping convention.

```ebnf
expression =
      let_expression
    | if_expression
    | lambda_expression
    | comparison_expression ;

let_expression =
    "let", "{", local_binding,
    { ";", local_binding },
    "}", "in", expression ;

local_binding =
    identifier, { identifier }, "=", expression ;

if_expression =
    "if", expression,
    "then", expression,
    "else", expression ;

lambda_expression =
    BACKSLASH, identifier, { identifier },
    "->", expression ;

comparison_expression =
    cons_expression,
    [ comparison_operator, cons_expression ] ;

comparison_operator =
    "==" | "!=" | "<" | "<=" | ">" | ">=" ;

cons_expression =
    additive_expression,
    [ ":", cons_expression ] ;

additive_expression =
    multiplicative_expression,
    { ( "+" | "-" ), multiplicative_expression } ;

multiplicative_expression =
    unary_expression,
    { "*", unary_expression } ;

unary_expression =
      "-", unary_expression
    | application_expression ;

application_expression =
    atomic_expression,
    { atomic_expression } ;

atomic_expression =
      integer_literal
    | boolean_literal
    | identifier
    | "(", expression, ")"
    | list_literal ;

list_literal =
    "[", [ expression, { ",", expression } ], "]" ;
```

### 8.2 Precedence and Associativity

Operators are ordered from highest to lowest precedence. The following table summarizes the same hierarchy described in Section 3.4:

| Precedence | Construct | Associativity |
|---|---|---|
| 1 | Parenthesized expressions | Explicit grouping |
| 2 | Function application | Left |
| 3 | Unary negation | Prefix |
| 4 | Multiplication | Left |
| 5 | Addition and subtraction | Left |
| 6 | Cons (`:`) | Right |
| 7 | Comparison and equality | Non-associative |

Conditional expressions, lambda expressions and `let` expressions are handled separately and require parentheses when used as operands of arithmetic operations or as function arguments.

Examples of required grouping:

```haskell
-- Expression fragments (not standalone program definitions):
-- double 3 + 2          => (double 3) + 2
-- double (3 + 2)        => double applied to (3 + 2)
main = 1 + (if True then 2 else 3)
```

The illustrative lines above demonstrate expression parsing; a complete source program still consists only of top-level definitions (Section 8.5).

### 8.3 Additional Rules

- Function application is represented as a sequence of atomic expressions and is left-associative.
- Parentheses override the default precedence rules.
- Lambda expressions may have multiple parameters, which are desugared into nested unary lambdas.
- Local binding groups are mutually recursive.
- List literals are desugared into nested `Cons` constructors ending in `Nil`.
- Chained comparison and equality operations are not supported.
- Expression parsing is bounded by the expected enclosing delimiter (e.g., `then`, `else`, `in`, `;`, `}` or a top-level `NEWLINE`) according to the active grammar production.
- The implementation should offer a separate `parse_expression` entry point, accepting one expression followed by `EOF`, for the user-selected evaluation expression. Conceptually, this entry point has the grammar `selected_expression = expression, EOF ;`.
- The expression grammar specifies token sequences; where two lexical tokens could merge (such as adjacent identifier characters), the source must contain a separator. Application does not use commas or function-call argument lists.
- A definition consisting only of a bare expression is not valid at top level.
- Variable-pattern equations do not require a match-time evaluation of the inspected argument; constructor-pattern equations may require evaluation to WHNF.
- The initial grammar does not include division, logical operators, string literals or floating-point literals.

### 8.4 Comments

Single-line comments begin with `--` and extend to the end of the current line.

The lexer must ignore comment contents while preserving newline boundaries between top-level definitions.

Comments are not represented in the AST or Core. Since `--` starts a comment, `10--2` is tokenized as `10` followed by a comment; subtraction of a negative value should be written `10 - -2`.

### 8.5 Program Structure and Function Equations

#### 8.5.1 Program Structure

A program consists of zero or more top-level definitions, separated by newline characters.

Each definition must occupy a single physical line. Blank lines and single-line comments are permitted. An expression does not continue onto a subsequent physical line in v0.1; multiline expressions are a deferred enhancement.

```ebnf
program =
    { NEWLINE },
    [ definition, { NEWLINE, { NEWLINE }, definition } ],
    { NEWLINE },
    EOF ;

definition =
      value_definition
    | function_equation ;
```

`NEWLINE` represents a line separator preserved by the lexer, while `EOF` represents the end of the source file.

Comments and horizontal whitespace are ignored by the lexer, except that line separators must be preserved.

#### 8.5.2 Value Definitions

A value definition associates an identifier with an expression and has no parameters.

```ebnf
value_definition =
    identifier, "=", expression ;
```

Example:

```haskell
answer = 42
```

#### 8.5.3 Function Equations

Functions are defined through one or more equations.

```ebnf
function_equation =
    identifier, { identifier }, final_pattern, "=", expression ;

final_pattern =
      identifier
    | "[", "]"
    | "(", identifier, ":", identifier, ")" ;
```

Constructor patterns are only supported in the last argument of top-level function equations.

Examples:

```haskell
double x = x * 2

length [] = 0
length (x:xs) = 1 + length xs
```

#### 8.5.4 Grouping Function Equations

Consecutive equations with the same function name form a single function definition. For grouping purposes, blank lines and comment-only lines are ignored: they do not terminate the current group. A top-level definition with a different name terminates it.

All equations within a group must:

- Have the same name.
- Have the same number of arguments.
- Appear consecutively in the source program.
- Use distinct parameter bindings within each equation.

Equation order is preserved because pattern matching is evaluated in source order.

A function name cannot be defined in multiple separate groups or simultaneously as a value definition. Each equation remains in its original source order for pattern matching, even if grouping happens after parsing.

#### 8.5.5 Validation

The parser recognizes individual definitions and equations.

A subsequent grouping and validation step verifies:

- Function equation grouping.
- Consistent function arity.
- Duplicate top-level definitions.
- Duplicate parameter names.
- Pattern position restrictions.

Non-exhaustive pattern matching is permitted. Failure to match any equation produces a runtime error.

#### 8.5.6 Program Entry Point

`main` is an optional ordinary top-level binding, not a reserved keyword. It is the default entry expression when executing a program without a separately selected expression.

- Parsing, semantic validation and Core lowering do not require `main`.
- A selected expression, when supplied, takes precedence over `main` and may refer to program-wide definitions.
- If neither `main` nor a selected expression is available, there is no execution entry point; frontend processing remains valid.
- The default entry expression is conceptually a reference to `main`, even when its binding contains a more complex expression.
- The entry point does **not** act like a `print` statement and does not determine whether the runtime observes a result to WHNF, to normal form, or only partially.
- Unlike Haskell's conventional executable entry point, `main` is not an `IO` action in this initial language, which has no input/output primitives.

#### 8.5.7 Limitations

The initial version does not support:

- Multiline definitions.
- Indentation-sensitive layout.
- Pattern matching in local `let` bindings.
- Pattern matching in lambda parameters.
- Nested constructor patterns.
- Pattern guards.
- Type signatures or module declarations.

### 8.6 Lexical Structure

#### 8.6.1 Identifiers

Identifiers must match the following regular expression:

```regex
[a-z][a-zA-Z0-9_]*
```

Identifiers are case-sensitive and cannot match reserved words.

#### 8.6.2 Integer Literals

Integer literals consist of one or more decimal digits:

```regex
[0-9]+
```

The language uses arbitrary-precision integers.

Negative numbers are represented through unary negation rather than signed integer tokens.

#### 8.6.3 Boolean Literals

Boolean literals are:

- `True`
- `False`

#### 8.6.4 Reserved Words

The following words are reserved:

`if`, `then`, `else`, `let`, `in`, `True`, `False`

The identifier `main` is not reserved.

#### 8.6.5 Operators and Delimiters

The lexer recognizes:

- Arithmetic: `+`, `-`, `*`
- Comparison: `<`, `<=`, `>`, `>=`, `==`, `!=`
- List construction: `:`
- Definition and lambda syntax: `=`, `->`, `\` (`BACKSLASH` token)
- Delimiters: `(`, `)`, `[`, `]`, `{`, `}`, `;`, `,`

Longer tokens take precedence over shorter tokens sharing the same prefix (maximal munch). In particular, `==` must be recognized as one token rather than two `=` tokens, and `--` is recognized as the start of a comment before treating either `-` separately.

The lexer also emits `NEWLINE` and `EOF` control tokens. Ordinary identifiers, non-negative decimal integer literals, and boolean keywords are distinguished during lexing.

#### 8.6.6 Whitespace and Newlines

Spaces and horizontal tabs are ignored outside token boundaries.

Line endings are normalized and represented using `NEWLINE` tokens.

Both LF and CRLF line endings are supported.

Each top-level definition must occupy exactly one physical line. Empty lines are permitted.

#### 8.6.7 Comments

Single-line comments begin with `--` and continue until the end of the line.

Comment contents are ignored, but the terminating newline is preserved.

#### 8.6.8 End of File

The lexer emits an `EOF` token after processing the source.

A final newline before `EOF` is optional.

#### 8.6.9 Source Locations

Every token records its starting source position, including:

- Line number.
- Column number.

Source positions are one-based.

AST nodes may carry a `SourceSpan` whose start is inclusive and whose end is exclusive. Coordinates must be positive integers, and the end must not precede the start. A span attached to a concrete syntax node must be non-empty, including empty-list expressions and patterns, whose delimiters occupy source text. An empty program may have an empty span. Nodes constructed without source locations may omit the span.

Source spans are diagnostic metadata and do not affect structural equality or hashing of AST nodes. Diagnostics use the offending child's span when available, falling back to the nearest enclosing span when that child has no source location.

#### 8.6.10 Lexical Errors

Unrecognized characters produce lexical errors containing their source location.

Lexical analysis does not validate expression structure, variable scope or function arity. These responsibilities belong to later compilation stages. Unexpected characters are lexical errors with their line and column; grammatically incomplete but otherwise tokenizable input is a parser error.

## 9. Frontend Boundary, Validation and Examples

### 9.1 Intended Pipeline

```text
Program source ──lexer/parser──> AST ──grouping + validation──> AST
                                            │
                                            ▼
                                      desugaring
                                            │
                                            ▼
                                          Core

Selected expression ──expression parser──> Expression AST
                  ──resolve against program bindings──> Core expression
```

The exact implementation order of grouping, name resolution and lowering will be settled in B02.3–B02.9; the pipeline must preserve source positions for diagnostics where feasible. The selected-expression parser reuses the same expression grammar, but is invoked separately from the parser for top-level definitions.

### 9.2 Preliminary Semantic Validation

Reject: duplicate names in one scope; duplicate parameter binders; inconsistent arities within equation groups; separated groups reusing a top-level name; unknown identifiers; constructor patterns outside the supported position. Do **not** reject recursive dependencies simply for being cyclic, or non-exhaustive matching simply for being non-exhaustive.

These frontend responsibilities are split between structural validation and name resolution. The AST structural validators check node and field types, container shapes, identifiers, supported operators, source spans, duplicate binders and definition groups, consistent equation arities, and pattern restrictions. They do not resolve references: an otherwise well-formed reference to an unknown identifier passes structural validation and must be rejected by the later semantic name-resolution stage. Successful structural validation does not imply that a program has resolved names or can execute without runtime errors.

Runtime responsibilities include: type errors in primitives and conditions, pattern match failures, nontermination/blackhole behavior, exact evaluation order, environment allocation and result observation. The default entry choice (`main` or a selected expression) is independent of the observation depth: for lazy strategies, displaying only WHNF is not the same as forcing an entire list.

### 9.3 Examples

#### 9.3.1 Valid Program and Selectable Entry Expression

```haskell
-- Simple higher-order function
map f [] = []
map f (x:xs) = f x : map f xs

double x = x * 2
```

Selected expression: `map double [1, 2, 3]`.

#### 9.3.2 Valid Program with Default Entry Point

```haskell
isEven n = if n == 0 then True else isOdd (n - 1)
isOdd n = if n == 0 then False else isEven (n - 1)
main = isEven 10
```

#### 9.3.3 Valid Recursive Local Bindings

```haskell
main = let { x = 1; y = x + 2 } in y
```

#### 9.3.4 Valid Non-Strict Variable Pattern (CBN/CBNeed)

```haskell
f x = 10
f [] = 20
loop = loop
main = f loop
```

The first equation matches without evaluating `loop` under CBN or CBNeed. Under CBV, evaluation of the argument can diverge before entering the function.

#### 9.3.5 Valid Equation Group with a Blank Line or Comment

```haskell
map f [] = []

-- Non-empty list
map f (x:xs) = f x : map f xs
```

#### 9.3.6 Invalid Programs in v0.1

```haskell
map double [1, 2, 3]  -- Bare top-level expression
```

```haskell
f x x = x             -- Duplicate parameter
```

```haskell
first (x:xs) ys = x   -- Constructor pattern not in final position
```

```haskell
main = 1 < 2 < 3      -- Chained comparisons
```

## 10. Deferred Enhancements / Future Work

The following items are **recorded explicitly but excluded from B02**. They are design options rather than commitments to a particular implementation schedule:

1. **Multiline expressions**, beginning with continuations inside parentheses and list delimiters.
2. **Indentation-sensitive Haskell-style layout**, particularly `let` blocks without braces/semicolons and multiline function bodies. This requires a layout-aware lexical/parsing layer but should not change the language's underlying Core semantics.
3. **Worksheet / REPL-like mode** allowing several bare expressions to be entered and executed individually, while the existing source-program parser continues to accept definitions only.
4. **Generalized `CoreCase`** potentially subsuming `CoreIf`.
5. **Saturated multi-argument call optimization**, retaining unary lambdas and binary applications in Core and measuring semantic steps separately from physical allocations.
6. **Broader patterns** (other argument positions, nested patterns, local pattern equations), plus optional exhaustiveness/redundancy diagnostics.
7. **Optional additional operators and data types**, subject to the experimental goals and available development time.

None of these enhancements should block implementation of the initial Source → AST → Core pipeline.
