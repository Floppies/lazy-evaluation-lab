# Core Evaluation Contract

**Status:** B04.1 draft  
**Scope:** Core abstract machine, CBV, CBN and CBNeed.

## 1. Evaluation and Demand

Core expressions are evaluated under a lexical environment and a selected evaluation strategy.

Evaluation, demand to weak head normal form (WHNF), and result observation are distinct operations.

`EvaluateCore(expression)` initiates evaluation of a Core expression in the current machine environment. It does not, by itself, guarantee that every returned runtime reference has already been forced to WHNF.

`Force(reference)` represents an explicit request to bring a runtime reference to WHNF. Its operational rules are introduced incrementally in B04 and B05.

`Return(reference)` represents an intermediate evaluation result delivered to the current continuation. The reference may designate an immediate value, an already evaluated runtime object, or an object requiring further evaluation.

## 2. Weak Head Normal Form

For the supported language, WHNF exposes the outermost value form without recursively evaluating the contents of data constructors.

Examples of WHNF include:

- An evaluated integer or boolean.
- A function closure.
- A partially applied primitive function.
- A data constructor whose outermost form is known.

Some of these forms are implemented in later milestones.

WHNF is distinct from complete result materialization. Demand policies and constructor-field evaluation depend on the selected strategy.

## 3. Evaluation Contexts

A demand for WHNF may originate from:

- Function-position evaluation.
- Strict function-argument evaluation under CBV.
- Primitive arithmetic or comparison operands.
- Conditional predicates.
- The first argument of a saturated `seq` application.
- Constructor inspection during pattern matching.
- Result observation.

These contexts may require different continuation frames but share the abstract notion of WHNF demand.

Their exact operational rules are defined in subsequent B04–B06 milestones.

## 4. Result Observation

`Return` with an empty evaluation stack does not automatically imply `COMPLETED`.

When the root result is ready for observation, the result consumer applies the configured `ResultPolicy`:

- `WHNF_ONLY`: observe the result at WHNF.
- `ASK_AT_WHNF`: expose an explicit consumer decision point.
- `MATERIALIZE_COMPLETE_VALUE`: request recursive materialization subject to result limits.

Result observation must not silently alter the evaluation strategy.

The B03 `WHNF_PENDING` batch stop reason is provisional and does not guarantee that the referenced value is already in WHNF.

Canonical result observation and terminal-state transitions are completed in B04. Recursive materialization of lists requires B06 support.

## 5. Milestone Boundaries

B04 establishes the initial Core operational evaluator, explicit continuations, and supported WHNF-demand rules.

B05 introduces the complete thunk, update, sharing, and blackhole machinery required by non-strict evaluation.

B06 introduces executable constructors, pattern matching, and recursive list programs.

B07 introduces comparable operational metrics.

These features must not be simulated as completed before their corresponding operational rules exist.


## 6. Controls and Continuations

The Core machine uses explicit continuation frames rather than
the Python call stack to represent pending evaluation work.

### 6.1 Control Responsibilities

- `EvaluateCore(expression)` evaluates an expression using the
  current lexical environment.
- `Return(reference)` delivers a runtime reference to the
  pending continuation. It does not guarantee WHNF.
- `Force(reference)` requests evaluation of a reference to WHNF.
  The current stack retains the continuation awaiting the result.
- `InitializeCoreBindings(bindings, next_index)` represents
  initialization work for a recursive binding group.

One successful `step()` performs one abstract-machine transition.
A demand or function application may require multiple transitions.

### 6.2 Application Continuations

`ApplyFunctionFrame` retains the unevaluated argument expression
and its call-site environment while the function is evaluated.

Before applying the function, its reference must denote an
applicable value in WHNF. If necessary, the machine requests WHNF
through `Force` while preserving the pending continuation.

Under CBV, `ApplyArgumentFrame` retains the function reference
while the argument is evaluated strictly. The resulting value is
then bound to the function parameter.

Under CBN and CBNeed, the argument is deferred according to the
selected strategy. The argument expression and call-site
environment must remain available until the deferred runtime
representation has been constructed.

Function bodies use the closure's lexical environment extended
with the parameter binding, never the caller's local environment.

### 6.3 Conditional Continuations

`IfFrame` retains both branches and the lexical environment in
which they must be evaluated.

The condition is demanded to WHNF. Once its boolean value is
known, only the selected branch is evaluated.

The unselected branch is neither evaluated nor forced.

### 6.4 Stack and State Invariants

Continuation frames are immutable. Their payloads preserve the
references, expressions and lexical environments needed to
resume evaluation.

The continuation stack is LIFO. A nested computation may push
additional frames without discarding its enclosing continuation.

A successful transition must preserve the previous logical
state. Mutable stack and heap storage are isolated using the
existing snapshot mechanism.

The active `Return` control is consumed according to the top
continuation frame. A root `Return` with an empty stack belongs
to the result-observation boundary, not automatic completion.

### 6.5 Deferred Frames

Additional continuation families are introduced with the
operational rules that require them:

- Primitive operands and conditionals: B04.5.
- Recursive local initialization: B04.6.
- Saturated `seq` applications: B04.7.
- Result consumption: B04.8.
- Thunk updates and sharing: B05.
- Constructors and pattern matching: B06.

No operational support for these deferred constructs is implied
by this contract.


## 7. Evaluation Strategies and Binding Contracts

### 7.1 Shared Core Representation

CBV, CBN and CBNeed evaluate the same validated `CoreProgram`.

The evaluation strategy determines argument evaluation, local
binding initialization, deferred computations and result reuse.

It does not modify Core syntax or lexical name-resolution rules.

### 7.2 Global Bindings

All `CoreProgram` bindings form one mutually recursive global scope.

Before evaluating the selected entry expression, the runtime makes
every global binding addressable.

Global RHS expressions are activated on demand under all three
strategies, including CBV.

Registering a global binding does not imply evaluating its RHS.

A global RHS is demanded only when an evaluation context requires
its value. Merely selecting an entry point must not evaluate
unrelated global definitions.

For example:

```haskell
loop = loop
main = 42
```

Evaluating `main` must not activate `loop`, regardless of strategy.

The selected expression may refer to global definitions declared
later in source order.

Global definitions remain lexically visible to closures, without
requiring closures to capture the global environment.

### 7.3 Call by Value

CBV evaluates the function position before its argument.

Function arguments are evaluated strictly before parameter binding.
Applications evaluate successive arguments from left to right.

Evaluating a lambda produces a function value without evaluating
its body.

Entering a local `CoreLetRec` establishes the complete recursive
scope before strict initialization.

Function-valued lambda RHSs may be installed as closures without
executing their bodies. Other local RHSs are initialized strictly
in a deterministic source order.

A demanded global RHS is evaluated strictly, but unrelated global
RHSs are not initialized automatically.

The detailed handling of active recursive initialization and
cyclic dependencies is defined by the corresponding runtime rules.

### 7.4 Call by Name

CBN does not evaluate an ordinary function argument before
binding it.

Instead, the argument is represented as a deferred computation
associated with its lexical call-site environment.

When its value is required, the deferred computation is evaluated.

Repeated demands must not introduce automatic memoization.
Each demand may evaluate the original expression again.

Local recursive bindings are non-strict.

Direct aliases must preserve reference identity where required
without accidentally introducing call-by-need sharing.

The operational representation of suspensions belongs to B05.

### 7.5 Call by Need

CBNeed initially defers ordinary function arguments and
non-strict local RHSs.

A deferred computation retains its lexical environment.

The first demand evaluates the computation, and the result is
made available for subsequent demands through a shared identity.

Repeated demands must not reevaluate an already updated thunk.

Thunk states, updates, indirections, sharing and blackhole
detection belong to B05.

### 7.6 Lexical Scope and Shadowing

Every strategy uses the same lexical binding rules.

A local binding shadows an enclosing binding with the same name.

Function applications extend the closure's definition-site
environment with the argument binding.

The caller's local scope does not become the parent scope of
the function body.

Global bindings are resolved separately from captured local
references.

The predefined `seq` binding belongs to an outer lexical scope
and may be shadowed by user definitions.

### 7.7 Explicit Demand

Demand to WHNF is distinct from binding a reference.

Function position, strict primitive operands, conditional
predicates, saturated `seq` and result observation introduce
explicit demand requirements.

A demand must preserve the evaluation strategy.

CBN must not gain implicit memoization through aliases or frames.
CBNeed must preserve sharing identity across repeated demands.

An application of saturated `seq` requires its first argument
to reach WHNF before continuing with the second argument.

CBV still follows ordinary strict argument evaluation.

### 7.8 Operational Boundaries

B04 introduces the initial executable Core rules and program
initialization.

B04 does not claim complete non-strict evaluation merely
because CBNeed and CBN are accepted configuration values.

B05 implements the complete suspension, thunk, update, sharing
and blackhole machinery.

B06 implements constructors, case expressions and recursive
list-program execution.

Dynamic strategy equivalence and experimental cost comparisons
must be verified independently from these static contracts.
