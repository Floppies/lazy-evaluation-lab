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

## 8. Operational Invariants and Acceptance Criteria

### 8.1 Transition Invariants

Every successful Core evaluator transition must:

1. Apply exactly one abstract-machine rule.
2. Preserve the previous logical execution state.
3. Produce an independent successor state.
4. Advance the state ID and transition index.
5. Increment the evaluator transition counter for an
   evaluator transition.
6. Preserve lexical scoping and the configured strategy.
7. Retain pending continuations until they are consumed.
8. Report the applied rule through a stable rule identifier.

A transition may update the control, environment, heap and stack
as required by its operational rule.

Instrumentation must not determine the selected semantic rule.

### 8.2 Reference Return and WHNF Demand

`Return(reference)` delivers a runtime reference to the current
continuation. It does not independently certify that the
referenced object is in WHNF.

A continuation requiring WHNF must arrange an explicit demand
through `Force(reference)` or an equivalent documented sequence
of machine transitions.

After demand is satisfied, the continuation must resume without
repeating the same demand indefinitely.

The implementation must distinguish the stage before WHNF
demand from the stage after successful demand.

The exact continuation representation is defined before
implementing application and forcing rules.

### 8.3 Recursive Global Initialization

The evaluator must not start executing the selected entry
expression before its global lexical scope is established.

All global names must be addressable before any selected global
RHS is demanded.

Global RHS expressions are activated on demand, including
under CBV. Initializing the global scope must not evaluate
unrelated global RHS expressions.

The predefined identifier scope is outside user-defined
global and local scopes. Ordinary lexical shadowing applies.

### 8.4 Entry-Point Contract

Compiling a Core program does not require executing it.

The runtime is responsible for selecting an entry expression
or named global entry point.

The default entry may be `main` when that binding exists.
Programs without `main` remain valid compilation inputs.

If no valid execution entry has been selected, execution
initialization must fail with an explicit diagnostic rather
than silently selecting an unrelated definition.

The exact initialization API and diagnostic types are defined
during B04.2.

### 8.5 Error and Unsupported-State Handling

An unsupported operational construct must not be treated
as successfully evaluated.

Invalid machine states and unsupported machine kinds must
produce explicit diagnostics.

A failed transition must not leave partial mutations in the
input execution state.

Step and result limits must not be classified as proof of
program divergence.

### 8.6 B04.1 Acceptance Criteria

B04.1 is complete when:

- The responsibilities of `EvaluateCore`, `Return`, `Force`
  and `InitializeCoreBindings` are documented.
- WHNF demand and result observation are distinguished.
- Continuation responsibilities and lexical environments
  are documented.
- CBV, CBN and CBNeed contracts are explicitly separated.
- Recursive global initialization is demand-driven.
- Local CBV `CoreLetRec` initialization is strict.
- The invariant between successful forcing and continuation
  resumption is recorded.
- Milestone boundaries for B04, B05 and B06 remain intact.
- Existing B03 regression tests pass.

Completing these contracts does not establish operational
correctness of rules that have not yet been implemented.

### 8.7 B04.2 Readiness

B04.2 may begin by implementing the operational initialization
of a Core program:

- Establish the predefined identifier scope.
- Make the complete recursive global group addressable.
- Preserve source-order and lexical binding identities.
- Select an explicit or default execution entry.
- Avoid evaluating unrelated global RHS expressions.
- Produce a valid initial `ExecutionState`.
- Keep initialization transitions observable.

The concrete representation of pending global computations
must satisfy the strategy contracts without prematurely
implementing B05 thunk updates or sharing.


## 9. Core Program Initialization

### 9.1 Initial-State Factory

`create_initial_core_state(program, config, session_id, entry)`
creates the initial state for a validated Core program.

The initial machine has:

- `ExecutionPhase.INITIALIZATION`
- `ExecutionStatus.RUNNING`
- `InitializeCoreBindings` as its control
- Empty heap and continuation stack
- Zero transition and evaluator counters

The factory does not evaluate program expressions or install
global bindings.

### 9.2 Entry Selection

The default entry is the global binding `main`.

A caller may select another global binding by name or provide
an explicitly validated Core expression.

If no default or explicit entry is available, initialization
fails with a diagnostic.

The selected entry expression is retained by
`InitializeCoreBindings` until global initialization finishes.

The execution entry is a user-facing selection.

If the user does not provide an explicit entry and `main` exists,
`main` is selected by default.

The user may instead provide or select another expression, even
when `main` exists. The application layer is responsible for
converting that selection into a validated Core expression.

If neither `main` nor an explicit entry is available, execution
initialization fails rather than selecting an arbitrary binding.

User-facing diagnostics for invalid selected expressions are
defined during application integration. It is assumed that when
the expressions reaches this stage it has been validated.

### 9.3 Initialization Boundary

Subsequent initialization transitions must establish the
predefined scope and make all global bindings addressable
before execution of the selected entry begins.

Global RHS activation remains demand-driven under every
evaluation strategy.

Creating an initial state is not equivalent to completing
global initialization.

### 9.4 Global Scope Reservation

Global initialization separates address reservation from RHS
installation and evaluation.

The predefined environment forms an outer lexical scope.
User-defined globals form a child scope and may shadow
predefined identifiers.

Each predefined function is represented initially by an
immutable runtime function object stored in the simulated heap.

Every user-defined global receives a stable one-slot heap
address containing `Reserved` before any RHS is installed.

Source-order reservation is deterministic. No global RHS is
evaluated during this operation.

The predefined function objects introduce a fixed
initialization cost in abstract heap slots. Experimental
metrics must distinguish this baseline from allocations
caused by program execution.

The reservation helper mutates an owned heap. When invoked
by the evaluator, it must operate on isolated successor-state
storage.

Pending global RHS representations and initialization
transitions are implemented in subsequent B04.2 subtasks.

### 9.5 Installing Global RHS Representations

After every global binding has a stable reserved address, the
runtime installs RHS representations without evaluating them.

A non-lambda global RHS is represented by `PendingGlobal`,
which retains the original Core expression.

A top-level lambda RHS is installed directly as a `Closure`.
Its body is not evaluated, and the closure captures no local
bindings. Global references are resolved through the separate
global environment when the function is applied.

Installation preserves the original heap address and its
allocated slot capacity. It does not allocate a second object
for the global binding.

`PendingGlobal` uses one abstract heap slot. The host memory
occupied by its Core AST is outside the simulated heap.

`PendingGlobal` does not implement forcing, memoization,
updates or strategy-specific sharing.

Global RHS demand remains independent from argument
strictness and local `CoreLetRec` initialization.

Each installation operation modifies an owned heap. The
evaluator must use isolated successor-state storage when
applying initialization transitions.

The operational installation sequence and entry-expression
activation are implemented in B04.2.4.

### 9.6 Operational Initialization Transitions

Global initialization is performed through explicit Core
machine transitions.

`InitializeCoreBindings` tracks whether the global scope has
been reserved and which RHS must be installed next.

The initialization sequence consists of three rule families:

1. `CORE_INIT_RESERVE_GLOBAL_SCOPE` creates all predefined
   and user-defined global references.
2. `CORE_INIT_INSTALL_GLOBAL` installs one global RHS
   representation per transition.
3. `CORE_INIT_ENTER_ENTRY` switches the machine to the
   evaluation phase with the selected entry expression.

All global addresses exist before the first RHS installation.

Global RHS installation preserves stable object identities
and does not evaluate the stored expressions.

Each successful initialization transition produces an
independent successor `ExecutionState`, increments the
transition index and evaluator-transition counter, and
reports a stable rule identifier.

Initialization transitions count toward the execution
step budget. They are not automatically classified as
semantic reductions of the source program.

Once initialization finishes, the selected entry is
evaluated through the ordinary Core machine rules.

For a program with N global bindings, initialization
requires N + 2 machine transitions.

The current milestone does not yet implement variable
forcing or demand-driven evaluation of pending global
RHS expressions.

## 10. Free Variables and Closure Capture

### 10.1 Iterative Free-Variable Analysis

`free_variable_names(expression)` computes the set of names
that are free relative to a Core expression.

The traversal is iterative and does not rely on the Python
call stack.

Lexical binders are handled as follows:

- `CoreLam` binds its parameter within its body.
- `CoreLetRec` binds all group names in every RHS and the
  group body.
- `CoreCase` alternative binders are visible only within
  their corresponding alternative bodies.
- Nested scopes and shadowing are tracked independently.

The analysis does not modify the Core expression, runtime
environment, heap or execution state.

Global and predefined names may appear in the returned set.
They are not removed by this structural analysis.

### 10.2 Capture Selection

Free-variable discovery and runtime capture selection are
separate operations.

Only free names that resolve to visible local bindings
may be included in a closure's captured-local environment.

Global and predefined bindings are resolved through the
global lexical environment instead.

Selective local capture and runtime closure allocation
are completed in subsequent B04.3 subtasks.

### 10.3 Selective Local Capture

`select_free_local_names()` identifies which free variables
of a `CoreLam` resolve to local lexical bindings.

The analysis receives:

- The lambda expression.
- Its definition-site environment.
- The global environment used as the lexical boundary.

Only bindings found between the definition environment and
the global environment are eligible for capture.

The global environment and its predefined parent scope are
excluded from captured locals.

Local shadowing takes precedence over global and predefined
bindings, even when the identifiers have identical names.

The global environment must be an ancestor of the definition
environment, or be the definition environment itself.

The function validates that every remaining free identifier
resolves through the global scope.

The result is a sorted tuple of local names, providing
deterministic capture order and closure allocation sizes.

The operation does not evaluate references, allocate heap
objects, or modify lexical environments.

Runtime closure construction and allocation are completed
in B04.3.3.

### 10.4 Closure Construction and Heap Allocation

`allocate_closure()` integrates free-variable analysis, selective
local capture, closure construction and simulated heap allocation.

The operation:

1. Identifies the free local names of the lambda.
2. Captures their existing runtime references.
3. Constructs an immutable `Closure`.
4. Allocates a heap cell with exactly the required capacity.

The abstract allocation size is:

`1 + number_of_captured_local_references`

Global and predefined references are not stored in
`Closure.captured_locals`.

Captures preserve runtime reference identity. The allocation
operation does not dereference, force or evaluate captured
values, and does not execute the lambda body.

No heap mutation occurs before free-name selection and closure
construction have completed successfully.

The helper mutates its supplied heap. Evaluator transitions
must call it on snapshot-isolated successor storage.

Direct closure allocation assumes that the definition-site
environment already contains all required local references.

Recursive local binding groups require additional reservation
and installation rules, introduced in B04.6. This helper does
not itself initialize recursive binding groups.

Integration with `EvaluateCore(CoreLam)` belongs to B04.4.

### 10.5 Nested Closures and Lexical Scope

Nested Core lambdas produce distinct closures when evaluated.

Each closure captures only the free local references required
by its own lambda expression.

A parameter bound by an outer function may become a free
local variable of an inner lambda.

For example:

```haskell
main = \x -> \y -> x + y
```

The outer closure captures no local references.

After the outer function is applied, the inner closure
captures the reference bound to `x`.

When the inner function is applied, its call environment
combines:

- The global lexical environment.
- The inner closure's captured local references.
- The current argument binding.

Local captured references shadow global bindings with
the same names.

The caller's unrelated local environment is not inherited.

Closure construction does not evaluate lambda bodies or
dereference captured heap references.

### 10.6 B04.3 Completion Criteria

B04.3 establishes the infrastructure for selective Core
closure allocation:

- Iterative free-variable analysis.
- Correct handling of nested lexical scopes.
- Separation of local captures from global references.
- Deterministic capture selection.
- Heap allocation with exact abstract slot capacity.
- Stable captured reference identity.
- Independent execution-state snapshots.
- Integration tests with compiled nested lambdas.

This infrastructure does not yet implement operational
function application.

Evaluation of `CoreLam` and `CoreApp`, continuation handling,
and strategy-specific argument demand belong to B04.4.

Local recursive binding initialization remains in B04.6.

## 11. Initial Core Expression Evaluation

### 11.1 Variable Evaluation

`CORE_EVAL_VARIABLE` evaluates `CoreVar(name)` by resolving
the name in the current lexical environment.

The operation returns the existing runtime reference.

Variable evaluation does not:

- Allocate a new heap object.
- Dereference the resulting heap cell.
- Force a pending global RHS.
- Establish that the result is in WHNF.

Local bindings shadow global and predefined bindings through
ordinary lexical lookup.

### 11.2 Lambda Evaluation

`CORE_EVAL_LAMBDA` evaluates a `CoreLam` by allocating a
closure in the simulated heap.

The closure retains its Core lambda and captures only the
required free local references from the definition-site
environment.

The allocation size is determined by the number of captured
local references.

Lambda evaluation does not execute the lambda body or
force captured references.

A lambda already installed as a global closure is accessed
through `CORE_EVAL_VARIABLE`; it is not reconstructed.

### 11.3 Transition Semantics

Both rules produce `Return(reference)`.

Successful transitions:

- Preserve the previous execution state.
- Advance the state ID and transition index.
- Increment the evaluator transition counter.
- Report their stable rule identifier.

Heap mutations take place on isolated successor storage.

### 11.4 Current Operational Boundary

Variable lookup and lambda evaluation are supported.

Function application, pending-global forcing, and continuation
resumption are not yet implemented by these rules.

A root `Return` referring to `PendingGlobal` must not be
interpreted as a value already in WHNF.

Canonical root observation and forcing are completed by
subsequent B04 rules.

### 11.5 Application Evaluation

`CORE_EVAL_APPLICATION` handles `EvaluateCore(CoreApp(f, a))`.

The rule:

1. Pushes `ApplyFunctionFrame(a, call_site_environment)`.
2. Changes the control to `EvaluateCore(f)`.
3. Leaves the argument expression unevaluated.
4. Preserves the argument's lexical call-site environment.

The transition does not apply the function, evaluate its
argument, or force the function reference.

This initial application rule is shared by CBV, CBN and
CBNeed. Strategy-specific argument evaluation begins after
the function value has been obtained and demanded as needed.

Nested applications preserve continuation order through
the LIFO stack.

For an expression equivalent to `((f a) b)`, the machine
first pushes the frame for `b`, then the frame for `a`.

The frame for `a` must be consumed before the frame for `b`
during continuation processing.

### 11.6 Pending Application Continuations

After the function position has been evaluated, the control
may become `Return(function_reference)` while an
`ApplyFunctionFrame` remains on the stack.

This state is not a completed application.

A subsequent continuation rule must demand the function
reference to WHNF if required and then proceed according
to the selected evaluation strategy.

Continuation consumption and WHNF forcing are introduced
in subsequent B04.4 subtasks.

A root result-observation boundary must not consume or
discard pending application continuations.

### 11.7 WHNF Demand and Global RHS Activation

`Force(reference)` explicitly requests weak head normal form.

Supported WHNF representations currently include immediate
integers, immediate booleans, closures and predefined functions.

`Indirection` objects are followed without automatically
rewriting their containing heap cells.

A `PendingGlobal` activates its stored Core expression in
the global lexical environment.

The original caller environment is retained in an immutable
`GlobalDemandFrame` and restored when demand completes.

A global RHS may return another reference that still requires
forcing. The continuation distinguishes the stage before
WHNF demand from the stage after successful forcing.

Global RHS evaluation does not eagerly evaluate unrelated
globals.

No sharing, memoization or update to `PendingGlobal` is
performed by these rules.

A root `Return(reference)` is not ready for result observation
until the reference is recognized as WHNF.

Function application continuations are not yet consumed by
these demand rules. Their integration follows in B04.4.4.

Full CBNeed sharing, thunk updates and blackhole detection
remain responsibilities of B05.

### 11.8 Call-by-Value Function Application

Call-by-value function application uses explicit continuation
frames to separate function demand, argument evaluation and
closure-body execution.

An `ApplyFunctionFrame` retains the argument expression and
its original call-site environment.

When the function position returns, the machine explicitly
demands the function reference to WHNF.

After a Closure has been obtained, CBV evaluates the argument
in its original call-site environment.

The argument is also demanded to WHNF before parameter binding.

`ApplyArgumentFrame` retains the function reference, the caller
environment and the current demand stage.

When the argument is ready, the machine reconstructs the
closure's lexical call environment and enters its body.

A `RestoreEnvironmentFrame` preserves the caller environment
and restores it after the function body returns.

All frames are immutable. Demand-stage flags prevent repeated
forcing of already satisfied continuation demands.

Function and argument forcing do not introduce memoization
or sharing updates.

Only ordinary Closure application under CBV is implemented
by these rules.

Predefined function application, non-strict argument passing
and full thunk machinery are implemented in later milestones.

Nested curried applications preserve lexical capture and
LIFO continuation order.

### 11.9 B04.4 Integration and Acceptance

The initial Core function evaluator supports ordinary
call-by-value closure applications.

The implemented transitions preserve:

- Left-to-right function and argument evaluation.
- Strict WHNF demand for CBV arguments.
- Lexical closure capture and shadowing.
- Argument evaluation in the original call-site environment.
- Restoration of the caller environment after body execution.
- Global-function lookup and demand-driven global aliases.
- Explicit continuation order.
- Independent execution-state snapshots.
- Semantically equivalent execution across trace modes.

Global RHS evaluation remains demand-driven and does not
introduce sharing updates.

Applying a non-function value produces an explicit runtime
error.

Function application under CBN and CBNeed is not yet supported.
Their complete argument representations and demand behavior
remain responsibilities of later milestones.

Predefined function application, primitive operators,
conditionals and local recursive bindings are outside the
completed B04.4 scope.

## 12. Primitive Operations and Conditionals

### 12.1 Primitive Evaluation Initialization

`CORE_EVAL_PRIMITIVE_START` begins evaluation of a
`CorePrimOp` expression.

The rule preserves the primitive operator, the remaining
operand expressions, the original lexical environment and
the references of previously evaluated operands in a
`PrimitiveOperandsFrame`.

Operands are scheduled from left to right.

The first transition evaluates only the first operand.
No operand value is forced and no primitive computation
is performed by this rule.

The continuation distinguishes initial operand evaluation
from subsequent WHNF demand through an explicit demand flag.

### 12.2 Operational Boundary

B04.5.1 establishes the initial primitive evaluation
continuation.

The following rules are implemented separately:

- WHNF demand and operand continuation.
- Primitive operation execution and type checking.
- Conditional evaluation and branch selection.
- End-to-end primitive and conditional regression tests.

B04.5 does not introduce thunk memoization, shared updates
or recursive constructor evaluation.

### 12.3 Primitive Operand Demand

Primitive operands are evaluated strictly from left to right.

`PrimitiveOperandsFrame` retains:

- The primitive operator.
- The remaining unevaluated Core arguments.
- Runtime references for completed operands.
- The original lexical environment.
- The current WHNF demand stage.

After an operand expression returns a reference, the machine
requests WHNF explicitly through `Force(reference)`.

Once demand succeeds, the resolved reference is added to
the evaluated-argument tuple.

If more arguments remain, their evaluation begins in the
original lexical environment.

When all arguments reach WHNF, the continuation is removed
and the control becomes `ApplyPrimitive(operator, arguments)`.

The `CORE_PRIM_OPERANDS_READY` transition does not execute
the primitive operator.

Primitive type checking and computation are completed
in B04.5.3.

Demanding global references uses the existing global-demand
continuations and does not introduce memoization or updates.

The surrounding continuation stack remains intact while
nested operand evaluation is in progress.

Primitive operators are strict under every evaluation strategy,
even though complete non-strict function application belongs
to subsequent milestones.

### 12.4 Primitive Execution

`ApplyPrimitive` contains an operator and runtime references
whose operands have already reached WHNF.

`CORE_PRIM_EXECUTE` consumes this control and produces a
`Return` containing an immediate result.

The supported primitive operations are:

- Integer arithmetic: negate, +, -, *.
- Integer comparisons: <, <=, >, >=.
- Equality and inequality for two integers or two booleans.

Arithmetic and ordering require integer operands.

Equality and inequality require operands of the same supported
primitive type.

Unsupported operators, invalid arities and invalid operand
types produce explicit runtime errors.

Primitive execution does not allocate heap objects, modify
the continuation stack or perform additional forcing.

The operation is a single evaluator transition. Primitive
execution is strict regardless of the selected evaluation
strategy.

Constructor equality, structural list comparison and other
primitive data types are outside this initial implementation.

### 12.5 Conditional Evaluation

`CORE_EVAL_IF_CONDITION` evaluates a CoreIf expression by
pushing an IfFrame and evaluating its condition.

The frame retains both branches, the original lexical
environment and the condition demand stage.

The condition is strictly demanded to WHNF through
`CORE_IF_REQUIRE_CONDITION_WHNF`.

The demanded condition must be an ImmediateBoolean.
Other runtime values produce a type error.

After successful demand:

- CORE_IF_SELECT_THEN evaluates only the then branch.
- CORE_IF_SELECT_ELSE evaluates only the else branch.

The unselected branch is never evaluated by the conditional.

Both branches are retained as Core expressions until
selection, rather than being evaluated in advance.

The selected branch executes in the original lexical
environment of the conditional.

Conditional strictness applies to CBV, CBN and CBNeed.
It is independent of function argument strictness.

No heap allocation, sharing update or memoization is
introduced by conditional selection itself.

### 12.6 Stable Operational Rule Identifiers

Operational transitions use the RuleId StrEnum.

Rule identifiers describe completed machine transitions;
they do not determine which transition is executed.

The evaluator selects transitions from the current control,
continuation stack, runtime values and evaluation strategy.

Step returns a TransitionResult containing the RuleId.
TraceEntry preserves the same identifier when tracing is enabled.

RuleId values are stable strings to maintain compatibility
with exported traces and future visualization components.

TransitionKind remains a separate classification of the
transition's responsibility.

Adding a new operational rule requires extending RuleId
and documenting its semantic meaning.

A RuleId does not necessarily correspond to a source-level
semantic reduction. This distinction will be addressed
explicitly in B07 instrumentation.

### 12.7 B04.5 Integration and Acceptance

B04.5 completes the initial operational implementation
of primitive expressions and conditionals.

The evaluator supports:

- Strict, left-to-right primitive operand evaluation.
- Explicit WHNF demand for primitive operands.
- Integer arithmetic and unary negation.
- Integer ordering comparisons.
- Equality and inequality on supported primitive values.
- Explicit runtime type and arity errors.
- Strict evaluation of conditional predicates.
- Evaluation of exactly one conditional branch.
- Preservation of lexical environments across continuations.

Operational rules have stable identifiers represented by
the RuleId StrEnum.

Trace modes do not influence semantic execution.

Interrupted executions retain their control, heap,
environment and continuation stack, allowing evaluation
to resume from an existing ExecutionState.

Primitive evaluation and conditional selection do not
introduce thunk memoization or sharing updates.

B04.5 does not implement local recursive bindings,
predefined seq application or canonical result observation.

These responsibilities remain in subsequent milestones.

## 13. Local Recursive Bindings

### 13.1 CBV Local Scope Reservation

`CORE_LETREC_RESERVE_SCOPE` begins evaluation of a
CoreLetRec expression under Call by Value.

The rule reserves one stable heap address for each local
binding before evaluating any right-hand side.

Each address initially contains Reserved and occupies
one abstract heap slot.

All references are installed together in a child lexical
environment of the original local environment.

This makes every binding visible from every RHS, allowing
forward references and mutually recursive definitions.

The enclosing environment is preserved using
RestoreEnvironmentFrame.

The machine then enters InitializeLocalBindings, which
retains the binding group, body and source-order index.

Reservation does not evaluate any RHS or the let body.

Local binding cells may later point through Indirection
objects to separately allocated results, including closures
with captured references.

Strict RHS initialization and recursive dependency handling
are implemented in subsequent B04.6 subtasks.

CBN and CBNeed local bindings remain unsupported by this
CBV-specific rule.

The reservation rule does not implement thunk allocation,
sharing updates or blackhole detection.

### 13.2 CBV Local Function Initialization

Local bindings whose right-hand side is a `CoreLam` are
initialized without evaluating their function bodies.

`CORE_LETREC_INSTALL_FUNCTION` performs one function
initialization transition.

The evaluator:

1. Retrieves the binding's reserved heap reference from
   the current recursive environment.
2. Verifies that the binding cell is still `Reserved`.
3. Allocates a closure capturing only the required free
   local references.
4. Replaces the reserved cell with an `Indirection` to the
   allocated closure.
5. Advances the initialization index.

Closures may capture references to other bindings in the
same recursive group, including bindings that have not
yet been initialized.

Binding addresses remain stable throughout initialization.

When every binding in the group has been initialized,
`CORE_LETREC_ENTER_BODY` begins evaluating the let body
in the recursive environment.

The enclosing environment is restored through the
previously installed `RestoreEnvironmentFrame` when the
let expression finishes evaluating.

This behavior applies to CBV. Non-strict local binding
initialization is implemented separately.

### 13.3 CBV Strict Value Initialization

Local bindings whose RHS is not a `CoreLam` are
initialized strictly in source order under CBV.

The evaluator uses a `LocalValueInitializationFrame`
to preserve the binding reference, recursive environment,
and initialization continuation while evaluating a RHS.

The initialization process consists of three operational
rules:

- `CORE_LETREC_EVAL_VALUE`: Begins evaluating the RHS
  and pushes its initialization continuation.

- `CORE_LETREC_REQUIRE_VALUE_WHNF`: Explicitly demands
  the returned reference to WHNF through `Force`.

- `CORE_LETREC_STORE_VALUE`: Stores an `Indirection`
  from the reserved binding cell to the evaluated
  reference and resumes the next initialization step.

The binding cell must remain `Reserved` until its RHS
has reached WHNF.

The resulting reference may be an immediate integer,
an immediate boolean, or a heap reference to a
function value.

The evaluator does not allocate an additional heap
object for immediate values.

Only one local RHS is initialized at a time.

All names in the recursive group are lexically visible
from the beginning, but visibility does not imply that
their values have already been initialized.

Demanding a binding that remains `Reserved` produces an
explicit runtime initialization error.

Function-valued RHSs follow the separate initialization
rule defined in Section 13.2.

Strict initialization does not introduce deferred thunks,
memoization, or call-by-need update semantics.

The stable binding-cell representation is specified
in ADR-006.

### 13.4 Recursive Initialization Errors

Under CBV, local recursive binding groups are reserved
simultaneously but initialized strictly in source order.

Lexical visibility does not imply that a binding's value
has already been initialized.

Demanding a Reserved local binding during strict RHS
initialization raises `UninitializedLocalBindingError`.

This diagnostic identifies a premature demand on a local
binding, including direct self-dependencies, forward value
dependencies and strict recursive dependency chains.

The diagnostic does not require general graph-cycle
detection.

Function-valued RHSs may capture references to
uninitialized members of the same recursive group without
evaluating their function bodies.

A recursive function definition is therefore not itself
an initialization error.

Failed transitions must preserve the previous
ExecutionState, including its heap, stack and environments.

Nested `CoreLetRec` expressions establish independent lexical
scopes. `RestoreEnvironmentFrame` restores the enclosing
environment after a let body returns.

These initialization errors are distinct from the blackhole
and thunk-update semantics introduced for CBNeed in B05.

Error classification concerns operational behavior. The
chosen stable binding-cell representation is documented
separately in ADR-006.

### 13.5 B04.6 Integration and Acceptance

B04.6 completes the initial CBV operational support
for local recursive CoreLetRec binding groups.

The evaluator supports:

- Simultaneous reservation of local binding references.
- Stable one-slot binding anchors.
- Lexical shadowing of enclosing bindings.
- Recursive closure installation without body evaluation.
- Source-ordered strict initialization of non-lambda RHSs.
- Explicit WHNF demand before storing local values.
- Indirections preserving original binding addresses.
- Detection of premature demands on uninitialized bindings.
- Restoration of enclosing lexical environments.
- Execution through nested application and primitive frames.

Function-valued RHSs may capture other reserved bindings.
Their bodies are not evaluated during initialization.

Non-function RHSs are evaluated strictly to WHNF before
the corresponding binding is initialized.

The machine preserves snapshot isolation across all
local initialization transitions.

An execution interrupted during local initialization can
resume using the same ExecutionState and execution
configuration, subject to the remaining step budget.

Executing the same program in multiple batches must not
change its semantic result, allocation accounting, or
operational transition sequence.

Stable binding cells and indirection overhead are defined
by ADR-006.

B04.6 does not introduce lazy local bindings, thunk
memoization, sharing updates or general blackhole detection.

These remain outside the completed CBV local-binding scope.

## 14. First-Class Predefined `seq`

### 14.1 Partial Predefined Function Representation

Predefined functions are first-class runtime values.

An unapplied predefined function is represented by
`PredefinedFunction`.

A partially applied predefined function is represented
by `PartialPredefinedFunction`, which retains:

- The predefined function identifier.
- An immutable tuple of already applied RuntimeRef values.
- The original arity and remaining arity.

`PartialPredefinedFunction` is a heap object whose abstract
allocation size is one base slot plus one slot per captured
argument reference.

A partial application must retain at least one argument
and fewer arguments than the function's declared arity.

Creating this representation does not evaluate or force
its captured arguments.

Argument evaluation and demand follow the selected
evaluation strategy.

Under CBV, applied arguments must reach WHNF before
the partial application is constructed.

Under CBN and CBNeed, arguments may remain deferred.
Those strategies require their later runtime machinery.

Saturated applications do not produce
`PartialPredefinedFunction values`.

The operational rules for application and saturation
are defined in subsequent B04.7 sections.

### 14.2 CBV Partial Application of Predefined Functions

Under CBV, predefined functions use the ordinary CoreApp
evaluation path.

The function position is demanded to WHNF before the
argument is evaluated.

The argument is evaluated in the original call-site
environment and explicitly demanded to WHNF.

When applying an unapplied predefined function without
saturating its arity, CORE_PREDEFINED_PARTIAL_APPLY:

1. Creates a PartialPredefinedFunction retaining the
   evaluated argument reference.
2. Allocates the partial application with its exact
   required abstract slot capacity.
3. Removes the argument continuation.
4. Restores the caller's lexical environment.
5. Returns the reference to the partial application.

A partially applied predefined function is a valid WHNF
function value.

Partial applications do not evaluate the predefined
function's saturated behavior.

In B04.7.2, applying an additional argument that would
saturate seq remains unsupported.

Saturated application and its explicit demand rules are
implemented in B04.7.3.

CBN and CBNeed application are not implemented by these
CBV-specific transitions.
