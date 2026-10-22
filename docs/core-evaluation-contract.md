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
