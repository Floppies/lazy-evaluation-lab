## 1. Program Structure

- A program consists of top-level definitions.
- Each definition occupies a single line.
- Definitions are separated by newlines.
- A definition has the form:
  `name parameter1 ... parameterN = expression`
- Parameters are optional.
- Top-level recursion and mutual recursion are allowed.
- Modules, imports, and type declarations are not supported.

## 2. Literals and Identifiers

### Literals
- Integer literals: non-negative decimal integers.
- Boolean literals: `True` and `False`.
- Negative values are expressed using unary negation.

### Identifiers
- Identifiers must match `[a-z][a-zA-Z0-9_]*`.
- Identifiers are case-sensitive.
- Reserved words cannot be used as identifiers.

### Reserved Words
`if`, `then`, `else`, `let`, `in`, `True`, `False`.

## 3. Expressions and Operators

### Expressions
Expressions include:
- Integer and boolean literals.
- Variable references.
- Function applications.
- Unary and binary operations.
- Parenthesized expressions.

### Function Application
- Function application uses whitespace.
- Application is left-associative.
- Application has higher precedence than arithmetic operators.

### Operators
- Arithmetic: +, -, *
- Comparison: <, <=, >, >=
- Equality: ==, !=
- Unary negation: -

### Precedence
From highest to lowest:
1. Parenthesized expressions
2. Function application
3. Unary negation
4. Multiplication
5. Addition and subtraction
6. Comparison and equality

Arithmetic operators are left-associative.
Comparison and equality operators are non-associative.

### Limitations
Division and boolean logical operators are not supported
in the initial version.

## 4. Functions, Lambdas and Currying

### Function Definitions

Functions are defined using the syntax:

`name parameter1 ... parameterN = expression`

Functions may have one or more parameters.
Definitions without parameters represent values.

### Lambda Expressions

Anonymous functions use the syntax:

`\parameter -> expression`

Multiple parameters are supported:

`\x y -> expression`

The lambda body extends to the right within its
enclosing expression. Parentheses can be used
for explicit grouping.

### Currying

All functions are represented internally as unary
functions.

A function with multiple parameters:

`f x y = expression`

is desugared into:

`f = \x -> \y -> expression`

### Higher-Order Functions

Functions are first-class values and may be:

- Passed as arguments.
- Returned from other functions.
- Partially applied.
- Assigned to bindings.

### Scoping

Lambda parameters introduce local bindings.
References to variables from enclosing scopes are
allowed.

Duplicate parameters within the same function
parameter list are not permitted.

## 5. Conditional Expressions

### Syntax

Conditional expressions use the following syntax:

`if condition then expression1 else expression2`

### Rules

- Conditionals are expressions, not statements.
- Both `then` and `else` branches are mandatory.
- The condition must evaluate to a boolean value.
- Only the selected branch is evaluated.
- Conditionals have lower precedence than arithmetic
  operators and function application.
- Parentheses are required when using a conditional
  as a function argument or within an arithmetic operation.
- Nested conditionals are supported.

### Core Representation

Conditional expressions are preserved as `CoreIf` nodes.

`CoreIf` contains:
- A condition expression.
- A then-branch expression.
- An else-branch expression.

The runtime must evaluate the condition and select
exactly one branch, regardless of the evaluation strategy.

### Validation

The parser validates the presence and structure of all
three components. Since the initial language does not
include static type checking, a non-boolean condition
is rejected at runtime.

## 6. Bindings, Scope and Recursion

### Bindings

A binding associates an identifier with an expression.

Bindings do not determine when or how their associated expressions are evaluated. Evaluation behavior depends on the selected evaluation strategy (CBV, CBN or CBNeed).

The language supports both top-level and local bindings.

### Local Bindings

Local bindings are introduced using `let` expressions.

The syntax supports one or more bindings enclosed in braces and separated by semicolons:

```haskell
let { x = 10; y = 20 } in x + y
```

A single binding is also permitted:

```haskell
let { x = 10 } in x + x
```

The `let` construct is an expression and may appear wherever an expression is allowed, subject to the language's grouping rules.

Local binding groups are recursive: every binding is visible in the right-hand side of every other binding in the same group, including itself.

### Lexical Scoping

The language uses lexical scoping.

- Top-level bindings are visible throughout the program, independently of declaration order.
- Function parameters and lambda parameters introduce local bindings.
- Each `let` expression introduces a new lexical scope.
- Inner bindings may shadow identifiers from enclosing scopes.
- Duplicate binding names within the same scope are not allowed, except for consecutive equations belonging to the same function definition.
- References to undefined identifiers are rejected during semantic validation.

### Recursion

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

### Core Representation

Local binding groups will be lowered to a recursive binding representation, provisionally named `CoreLetRec`.

The Core representation must preserve lexical scoping, recursion and shadowing without imposing any particular evaluation strategy.

The exact representation and execution of recursive environments will be defined during the Core and runtime design stages.

---

## 7. Lists and Pattern Matching

### List Expressions

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

### List Representation

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

The runtime determines when constructor fields are evaluated, according to the selected evaluation strategy.

### Supported Patterns

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

### Pattern Position Restrictions

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

### Multiple Function Equations

A top-level function may be defined through multiple consecutive equations.

All equations must:

- Have the same function name.
- Have the same number of parameters.
- Appear consecutively in the source file.

Patterns are matched in source order.

A variable pattern matches any argument, while constructor patterns inspect the outermost list constructor.

If no equation matches, evaluation produces a pattern-matching error.

Exhaustiveness checking is not required in the initial implementation.

### Lazy Evaluation and Pattern Matching

Pattern matching on lists requires evaluating the inspected argument sufficiently to determine its outermost constructor.

Under CBN and CBNeed, matching a `Cons` constructor does not require evaluating its head or tail contents.

Under CBV, constructor fields are evaluated according to the strict evaluation rules of the runtime.

This distinction is important for studying demand, sharing, memory allocation and evaluation to Weak Head Normal Form (WHNF).

### Core Representation

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

The Core representation must preserve pattern matching order and the runtime's strategy-dependent evaluation behavior.

`CoreIf` will remain a separate construct for conditional expressions. Its possible replacement by a generalized `CoreCase` will be reconsidered during later development.

## 8. Formal Grammar (EBNF)

### 8.1 Expressions

The following grammar defines the supported expression syntax, including operator precedence, function application, conditional expressions, lambda expressions, local bindings and list literals.

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
    "\", identifier, { identifier },
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

Operators are ordered from highest to lowest precedence:

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

### 8.3 Additional Rules

- Function application is represented as a sequence of atomic expressions and is left-associative.
- Parentheses override the default precedence rules.
- Lambda expressions may have multiple parameters, which are desugared into nested unary lambdas.
- Local binding groups are mutually recursive.
- List literals are desugared into nested `Cons` constructors ending in `Nil`.
- Chained comparison and equality operations are not supported.
- The initial grammar does not include division, logical operators, string literals or floating-point literals.

### 8.4 Comments

Single-line comments begin with `--` and extend to the end of the current line.

The lexer must ignore comment contents while preserving newline boundaries between top-level definitions.

Comments are not represented in the AST or Core.

### 8.5 Program Structure and Function Equations

#### Program Structure

A program consists of zero or more top-level definitions, separated by newline characters.

Each definition must occupy a single physical line. Blank lines and single-line comments are permitted.

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

#### Value Definitions

A value definition associates an identifier with an expression and has no parameters.

```ebnf
value_definition =
    identifier, "=", expression ;
```

Example:

```haskell
answer = 42
```

#### Function Equations

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

#### Grouping Function Equations

Consecutive equations with the same function name form a single function definition.

All equations within a group must:

- Have the same name.
- Have the same number of arguments.
- Appear consecutively in the source program.
- Use distinct parameter bindings within each equation.

Equation order is preserved because pattern matching is evaluated in source order.

A function name cannot be defined in multiple separate groups or simultaneously as a value definition.

#### Validation

The parser recognizes individual definitions and equations.

A subsequent grouping and validation step verifies:

- Function equation grouping.
- Consistent function arity.
- Duplicate top-level definitions.
- Duplicate parameter names.
- Pattern position restrictions.

Non-exhaustive pattern matching is permitted. Failure to match any equation produces a runtime error.

#### Limitations

The initial version does not support:

- Multiline definitions.
- Indentation-sensitive layout.
- Pattern matching in local `let` bindings.
- Pattern matching in lambda parameters.
- Nested constructor patterns.
- Pattern guards.
- Type signatures or module declarations.

### 8.6 Lexical Structure

#### Identifiers

Identifiers must match the following regular expression:

```regex
[a-z][a-zA-Z0-9_]*
```

Identifiers are case-sensitive and cannot match reserved words.

#### Integer Literals

Integer literals consist of one or more decimal digits:

```regex
[0-9]+
```

The language uses arbitrary-precision integers.

Negative numbers are represented through unary negation rather than signed integer tokens.

#### Boolean Literals

Boolean literals are:

- `True`
- `False`

#### Reserved Words

The following words are reserved:

`if`, `then`, `else`, `let`, `in`, `True`, `False`

The identifier `main` is not reserved.

#### Operators and Delimiters

The lexer recognizes:

- Arithmetic: `+`, `-`, `*`
- Comparison: `<`, `<=`, `>`, `>=`, `==`, `!=`
- List construction: `:`
- Definition and lambda syntax: `=`, `->`, `\`
- Delimiters: `(`, `)`, `[`, `]`, `{`, `}`, `;`, `,`

Longer tokens take precedence over shorter tokens sharing the same prefix.

#### Whitespace and Newlines

Spaces and horizontal tabs are ignored outside token boundaries.

Line endings are normalized and represented using `NEWLINE` tokens.

Both LF and CRLF line endings are supported.

Each top-level definition must occupy exactly one physical line. Empty lines are permitted.

#### Comments

Single-line comments begin with `--` and continue until the end of the line.

Comment contents are ignored, but the terminating newline is preserved.

#### End of File

The lexer emits an `EOF` token after processing the source.

A final newline before `EOF` is optional.

#### Source Locations

Every token records its starting source position, including:

- Line number.
- Column number.

Source positions are one-based.

#### Lexical Errors

Unrecognized characters produce lexical errors containing their source location.

Lexical analysis does not validate expression structure, variable scope or function arity. These responsibilities belong to later compilation stages.