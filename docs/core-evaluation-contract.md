# Core Evaluation Contract

**Status:** B04 Core CBV evaluation and canonical observation implemented; audited with documented limitations.

**Scope:** Implemented Core CBV subset; planned CBN and CBNeed contracts.

This document retains the incremental B04 submilestone boundaries.
Those boundaries describe the responsibility of each stage, not
missing functionality in the completed B04 subset. See the
[B04 audit](audits/b04-audit.md) for verification evidence and limitations.

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

Integers, booleans and function values are supported in B04.
Executable constructors remain part of B06.

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

The implemented CBV rules are described below. Non-strict demand
and constructor matching remain part of B05, B06 and B11.

## 4. Result Observation

`Return` with an empty evaluation stack does not automatically imply `COMPLETED`.

When the root result is ready for observation, the result consumer applies the configured `ResultPolicy`:

- `WHNF_ONLY`: observe the result at WHNF.
- `ASK_AT_WHNF`: expose an explicit consumer decision point.
- `MATERIALIZE_COMPLETE_VALUE`: request recursive materialization subject to result limits.

Result observation must not silently alter the evaluation strategy.

In B03, `WHNF_PENDING` was a provisional boundary without a WHNF
guarantee. The current evaluator returns it only for a recognized
WHNF reference in a root `Return` with an empty stack. It leaves
the machine `RUNNING` until the result consumer completes observation.

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

An interrupted, nonterminal execution retains its control,
lexical environment, heap, continuation stack and pending
demand stages.

Provided that the execution budget has not been exhausted,
subsequent batches may resume from the returned ExecutionState
without restarting or repeating previously completed work.

Continuation restoration must preserve the original caller
environment, including across nested applications, primitive
operations and recursive binding initialization.

### 6.5 Deferred Frames

The initial B04.1 continuation plan assigned support to the
following operational milestones:

- Thunk updates and sharing: B05.
- Constructors and pattern matching: B06.

The B04 entries are now implemented as described below; saturated
seq uses the existing application continuations. Thunk updates,
sharing, constructors and pattern matching remain deferred.

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

### 7.9 Call-by-Need Demand Contexts

This section defines the demand behavior required by B05.
It is an operational contract, not an implementation-status
claim.

#### Evaluation and WHNF Demand

Evaluating a Core expression and demanding the resulting
runtime reference to WHNF are distinct operations.

`EvaluateCore(expression)` may produce a reference to a
deferred computation without executing that computation.

`Return(reference)` passes an existing runtime reference
to the current continuation. It does not guarantee WHNF.

`Force(reference)` requests WHNF and must preserve sharing
when the reference designates a Call-by-Need thunk.

#### Demand Contexts

Under CBNeed, WHNF is required by:

- Function position before application.
- Strict primitive arithmetic and comparison operands.
- Conditional predicates before branch selection.
- The first argument of a saturated predefined `seq`.
- Root result observation and other explicit observation
  requests requiring WHNF.

Ordinary function arguments are not evaluated solely
because they are applied to a function.

Local recursive bindings are established without strictly
evaluating their right-hand sides.

Global bindings remain demand-driven. Under CBNeed,
demanded global computations must participate in
memoizing evaluation.

#### Non-Demand Operations

The following operations must not independently force a
deferred computation:

- Resolving a variable to its runtime reference.
- Capturing a reference in a closure.
- Binding an ordinary function parameter.
- Constructing a deferred local binding.
- Creating a partial application of predefined `seq`.
- Returning a reference to an enclosing continuation.

These operations may be followed by an explicit demand
introduced by the surrounding evaluation context.

#### Strategy Independence

Demand contexts are determined by the semantics of Core
constructs and predefined functions, not by tracing,
metrics, or result presentation.

CBV retains strict argument evaluation and strict local
value initialization.

CBNeed introduces deferred evaluation and memoization.

CBN remains a separate B11 implementation and must not
inherit CBNeed updates implicitly.

Executable constructor inspection and recursive value
materialization remain outside B05.

### 7.10 Call-by-Need Thunk Lifecycle

This section specifies the semantic lifecycle of Call-by-Need
thunks. Concrete runtime classes and transition rules are
introduced incrementally during B05.

#### Thunk States

A deferred computation has three conceptual lifecycle states:

- PENDING: The computation has not been entered.
- EVALUATING: The computation is currently being evaluated.
- UPDATED: The computation has reached WHNF and its result
  is available for sharing.


UPDATED is represented by replacing the one-slot thunk
anchor with an Indirection to the resulting WHNF reference.

No distinct UpdatedThunk heap object is required.

#### First Demand

The first demand of a PENDING thunk initiates evaluation in
its captured lexical environment.

The thunk becomes EVALUATING before its expression is
evaluated. The machine must preserve the continuation needed
to install the result when WHNF is reached.

Merely looking up, passing, or capturing a thunk reference
does not enter the thunk.

#### Update and Sharing

A successful evaluation updates the original thunk address
to refer to its WHNF result.

The update must preserve the original ObjectId and allocated
slot capacity.

Subsequent demands through the original reference must
reuse the updated result without reevaluating the expression.

A thunk must not be updated with an unresolved result that
leads back to the same active computation.

#### Heap Representation

Thunk payloads are immutable.

Lifecycle transitions replace heap-cell contents in an
isolated successor state. They must never mutate payloads
shared with previous execution snapshots.

Recursive local bindings retain the stable one-slot anchors
defined by ADR-006. Separately allocated thunk objects may
be reached through these anchors when required by their
allocation capacity.

Every CBNeed deferred computation uses a stable one-slot identity anchor and a separately allocated payload.

The anchor preserves the shared identity of the computation.
The payload stores its Core expression and captured local
references.

Recursive local bindings may initialize an existing one-slot
Reserved anchor, as established by ADR-006.

After a successful update, the anchor contains an Indirection
to the WHNF result. The former payload may become unreachable
and eligible for future garbage collection.

#### Reentrant Demand

Demanding an EVALUATING thunk constitutes a blackhole
condition.

The operational detection and failure-reporting rules are
implemented in B05.7.

Exhausting an execution budget is not itself evidence of a
blackhole or divergence.

#### Strategy Compatibility

The existing CBV evaluation and global initialization
semantics must remain unchanged.

Under CBNeed, global computations and local deferred
bindings must participate in memoizing evaluation.

CBN does not inherit memoization from this contract.
Its non-sharing behavior remains part of B11.

#### Structural Thunk Representation

The Call-by-Need runtime introduces three immutable heap
object representations:

- `ThunkPayload` stores a deferred Core expression and a
  standalone environment of captured local references.
- `PendingThunk` is a one-slot identity anchor referring
  to a thunk payload awaiting evaluation.
- `EvaluatingThunk` is a one-slot identity anchor referring
  to a payload whose evaluation is in progress.

The abstract allocation cost of a ThunkPayload is one
base slot plus one slot per captured local reference.

The Core AST is retained by reference; its host memory is
not counted node by node in the simulated heap.

The anchor representations each require one abstract slot,
independently of the payload size.

Payloads and anchors are immutable. Their lifecycle will
be implemented through controlled heap-cell replacement
in subsequent B05 tasks.

The structural existence of these classes does not imply
operational Call-by-Need evaluation, memoization or
blackhole detection.

Selective capture, allocation helpers, forcing and
sharing are implemented in later B05 subtasks.

#### Selective Thunk Capture

Thunk payloads use the existing iterative Core free-variable
analysis to determine their lexical dependencies.

Capture selection is shared with function closures through
the runtime capture-selection module.

For each free variable, the runtime determines whether the
binding is resolved in a local lexical scope above the
global environment boundary.

Only free local bindings are captured.

Global and predefined bindings are resolved separately
through the runtime global environment.

Captured bindings preserve their original RuntimeRef
identity. Capture does not force, dereference, copy, or
evaluate referenced values.

The resulting captured environment is standalone and
contains no parent environment chain.

When a thunk is evaluated, its saved local references
will be layered over the global environment to reconstruct
the correct lexical scope.

Selection respects nested lambda parameters, recursive
let bindings, shadowing, and Core case binders.

Capture selection is deterministic and does not allocate
simulated heap objects. Heap allocation belongs to B05.2.3.

This structural support does not yet implement thunk
forcing or memoization.

#### Thunk Heap Allocation

Call-by-Need deferred computations use separate heap objects
for their stable identity anchors and evaluation payloads.

The `allocate_thunk` helper constructs the payload using
selective local capture and installs a PendingThunk anchor.

For fresh thunks, the runtime allocates the payload first
and then a new one-slot anchor. The returned reference
always identifies the anchor, never the payload.

For recursive local bindings, the runtime may provide an
existing one-slot Reserved anchor. The helper allocates the
payload and replaces the Reserved contents with PendingThunk,
preserving the anchor ObjectId and allocated capacity.

The abstract allocation cost of a fresh thunk is:

    2 + number_of_captured_local_references

A preallocated one-slot anchor contributes one of these slots
before initialization.

Payloads are allocated with exactly their required capacity.
Anchors always occupy exactly one abstract heap slot.

Expected validation errors are detected before new heap
allocations are performed.

The helper operates on a caller-owned heap. During evaluation,
the caller must use an isolated successor-state heap.

No expression is evaluated, forced, or memoized during
allocation.

Previously initialized anchors cannot be initialized again.

Global PendingGlobal conversion is handled separately in B05.6.

Payload reclamation is deferred to the future garbage collector.
Until then, unreachable payloads remain allocated in the
simulated heap and are included in its slot accounting.

##### Thunk Identity and Snapshot Preservation

Multiple environment bindings may reference the same thunk
anchor. Such aliases preserve shared identity without copying
the deferred computation.

Additional heap Indirections may also refer to a thunk anchor.
Updating the anchor does not eagerly rewrite those Indirections
or perform path compression.

Thunk lifecycle changes are represented by replacing the
anchor contents in an isolated successor heap:

- PendingThunk: the deferred computation has not started.
- EvaluatingThunk: the deferred computation is in progress.
- Indirection: the computation has been updated to its WHNF
  result.

Each replacement preserves the anchor ObjectId and its
one-slot allocation.

Heap snapshots retain their historical cell contents. Since
thunk payloads and anchors are immutable, successor snapshots
may safely share unchanged heap objects.

An updated anchor no longer references its former payload.
However, the payload remains allocated until garbage collection
reclaims it, provided it is unreachable from the roots that
must be preserved.

No operational forcing, automatic lifecycle transition,
indirection-path compression, or garbage collection is
implemented by this structural contract.

### 7.11 Thunk Update Continuations

#### UpdateFrame Responsibility

Call-by-Need evaluation uses an explicit UpdateFrame to
preserve the identity of a thunk undergoing evaluation.

The frame retains:

- The stable thunk reference to update.
- The lexical environment to restore after completion.
- The continuation stage distinguishing an initial RHS
  return from a completed WHNF demand.

The frame does not own or mutate the thunk payload.

#### Entering a Thunk

Forcing a PENDING thunk marks its identity cell as
EVALUATING before starting its expression.

The machine pushes an `UpdateFrame` and evaluates the RHS
in the thunk's saved lexical environment.

All changes occur in an isolated successor state.

#### Return and WHNF Verification

Returning from a thunk RHS does not imply that its
reference is already in WHNF.

If necessary, UpdateFrame requests explicit forcing and
waits for the resulting WHNF reference.

The thunk must not be updated before this requirement
has been satisfied.

#### Successful Update

After reaching WHNF, the machine replaces the thunk's
stable identity cell with an Indirection to the result.

The original ObjectId and allocated capacity remain
unchanged.

The machine then removes UpdateFrame, restores the saved
caller environment and returns the resulting reference.

Nested thunk evaluations use ordinary LIFO continuation
ordering and must preserve their enclosing frames.

#### Globals and Aliases

Under CBNeed, pending global RHS computations participate
in the same memoizing update protocol.

Existing CBV global demand behavior remains unchanged.

An update targets the identity cell of the demanded thunk.
Other aliases do not require eager rewriting or
indirection-path compression.

#### Blackholes and Execution Limits

A demand of an already EVALUATING thunk is a reentrant
demand and must be detected as a blackhole.

The exact error/status integration is deferred to B05.7.

A suspended execution with an active UpdateFrame remains
resumable. Reaching the execution-step budget is not
equivalent to detecting a blackhole.

Failed transitions must not partially mutate their input
ExecutionState.

#### Implementation Boundaries

Concrete UpdateFrame types, RuleIds and forcing transitions
are introduced during B05.4.

Heap updates and observable sharing are implemented in B05.5.

Recursive local and global binding integration belongs to
B05.6.

Advanced metrics and garbage collection are deferred to
B07 and B12 respectively.

### 7.12 Reference Programs and Acceptance

The B05 implementation must preserve the operational contracts
defined in Sections 7.9–7.11.

#### Reference Scenarios

The Call-by-Need regression suite must cover:

- Unused function arguments are not evaluated.
- Repeated demand of an argument shares its WHNF result.
- Unused local recursive bindings remain unevaluated.
- Mutually dependent local bindings resolve lexically.
- Repeated demand of a global RHS shares its result.
- Reentrant demand of an EVALUATING thunk detects a blackhole.
- Partial application of seq does not demand its first argument.
- Saturated seq demands its first argument to WHNF.
- Interrupted thunk evaluation resumes deterministically.
- Comparable terminating CBV and CBNeed programs produce
  equivalent canonical observable results.

#### Identity and Allocation

Each deferred computation has a stable one-slot identity
anchor and a separately allocated payload.

The payload retains the expression and the necessary lexical
references for evaluation.

Thunk lifecycle changes replace immutable anchor contents
without changing ObjectId or allocated slot capacity.

After a successful update, the anchor contains an
Indirection to the WHNF result. The former payload may
become unreachable.

Payload allocation and capture-slot accounting are specified
during B05.2.

#### Operational Verification

Tests must verify more than final result equality.

They must inspect appropriate RuleIds, thunk entry and update
behavior, reference identity, heap invariants, preserved
historical snapshots and resumed execution.

The same thunk must not evaluate its RHS more than once
after successful memoization.

CBV regression tests must continue to pass.

B05 does not claim complete constructor evaluation, CBN,
garbage collection or comparable experimental metrics.

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

`TraceMode` affects the recording of execution information,
not the selection or outcome of operational rules.

For the same initial state and execution configuration,
changing between FULL, EVENTS and METRICS_ONLY must preserve
semantic results, operational RuleId sequences, transition
counts and simulated heap allocation behavior.

Different trace modes may retain different amounts or forms
of instrumentation data without changing machine semantics.

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

### 8.5 Error and Unsupported-State Handling

An unsupported operational construct must not be treated
as successfully evaluated.

Invalid machine states and unsupported machine kinds must
produce explicit diagnostics.

A failed transition must not leave partial mutations in the
input execution state.

Step and result limits must not be classified as proof of
program divergence.

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
transitions are described in Sections 9.5 and 9.6.

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

Demand-driven evaluation is implemented separately in Section 11.7.

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
are implemented as described in Sections 10.3 and 10.4.

### 10.3 Selective Local Capture

`select_free_local_names()` identifies which free variables
of a `CoreLam` or a `CoreExpr` resolve to local lexical bindings.

The analysis receives:

- The expression.
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

Runtime closure construction and allocation are explained
in Section 11.2

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

Integration with `EvaluateCore(CoreLam)` belongs in section 13.

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

### 11.4 Variable and Lambda Rule Boundaries

Variable lookup and lambda evaluation are supported.

Variable and lambda rules do not themselves apply functions,
force pending globals or resume continuations. Those operations
are implemented by the separate rules in Sections 11.5-11.8.

A root `Return` referring to `PendingGlobal` must not be
interpreted as a value already in WHNF.

WHNF forcing is implemented in Section 11.7; canonical root
observation is implemented in Section 15.

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

Applying a non-function value produces an explicit runtime
error.

### 11.6 Pending Application Continuations

After the function position has been evaluated, the control
may become `Return(function_reference)` while an
`ApplyFunctionFrame` remains on the stack.

This state is not a completed application.

A subsequent continuation rule must demand the function
reference to WHNF if required and then proceed according
to the selected evaluation strategy.

Continuation consumption and WHNF forcing are implemented
as described in Sections 11.7 and 11.8.

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

Under CBV, demand-driven evaluation of a PendingGlobal
does not memoize its result or update the global binding.

CBNeed requires memoizing global demand through the thunk
update protocol defined in Section 7.11. The integration
of global bindings with this protocol belongs to B05.6.

CBN remains nonmemoizing and is implemented in B11.

A root `Return(reference)` is not ready for result observation
until the reference is recognized as WHNF.

These demand rules preserve pending application continuations.
Their consumption is implemented by the separate B04.4.4
application rules in Section 11.8.

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

Attempting to apply a runtime value that is not a supported
callable object produces an explicit runtime error.

Such a failure must preserve the input ExecutionState
without partially consuming or mutating its continuation
stack, lexical environment or heap.

### 11.9 Call-by-Need Closure Application

Under CBNeed, ordinary closure application evaluates and
demands the function position to WHNF before binding its
argument.

The function position must reach WHNF before any argument
thunk is allocated.

Function-position evaluation may involve lexical references,
heap Indirections, and demand-driven global bindings.

Once the function reference has reached WHNF, applying a
non-callable value raises an explicit runtime error without
allocating the argument thunk.

If the function position refers to a pending CBNeed thunk,
its value must be obtained through the thunk forcing protocol
defined in Section 7.11.

Operational forcing of PendingThunk is introduced in B05.4.
Until that support is available, such a demand remains an
explicitly unsupported execution path rather than a
non-callable-value error.

Once the function has been resolved to a Closure, the
argument Core expression is not evaluated or forced.

Instead, the evaluator allocates a deferred thunk using
the argument expression and its original lexical call-site
environment.

The thunk retains only the required free local references.
Its stable identity anchor is bound to the closure parameter.

The function body executes in the closure's lexical
environment, extended with the deferred argument binding.

The caller environment is preserved by an explicit
RestoreEnvironmentFrame and restored when the body returns.

Entering the closure body is represented by the
`CORE_CBNEED_ENTER_BODY` operational rule.

The transition preserves the original ExecutionState and
allocates the thunk on the isolated successor heap.

The argument remains PENDING until an evaluation context
explicitly demands its value.

A deferred argument captures its free local references from
the original call-site environment retained by
ApplyFunctionFrame, before the callee's parameter binding
is introduced.

The callee's definition-site environment is used to execute
its closure body, not to resolve free variables in the
argument expression.

Consequently, parameter shadowing in the callee does not
change the lexical meaning of an argument. Captured references
retain their original identity, including references to other
pending thunks.

Nested lazy applications may therefore construct thunks
whose payloads refer to other thunks without forcing them.
Global and predefined identifiers are resolved separately
and are not copied into the captured-local environment.

When a CBNeed closure body evaluates to another lambda,
the resulting Closure captures the required free local
references from its definition-site environment.

These captures may include references to pending argument
thunks created by earlier applications.

Restoring the caller's lexical environment does not
invalidate or evaluate references retained by a returned
Closure. The returned function remains in WHNF regardless
of whether its captured thunks have been forced.

Curried applications preserve the identity of captured
thunk references across successive function applications.

Each ordinary argument is deferred independently. A
later argument is not evaluated merely because an earlier
application returned a function.

Only references required by a nested lambda are captured.
Unused parameters are not retained by that lambda unless
needed by its expression.

Evaluating or observing a returned function does not
force its captured thunks. Demanding a captured thunk
remains the responsibility of the forcing rules in B05.4.

CBV continues to evaluate and force arguments strictly.

Call-by-Name application remains part of B11.

Forcing a deferred argument, update continuations and
memoization are implemented in B05.4 and B05.5.

Non-strict predefined function application, including
first-class seq, is implemented in B05.8.

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

The following rules are implemented separately:

- WHNF demand and operand continuation.
- Primitive operation execution and type checking.
- Conditional evaluation and branch selection.
- End-to-end primitive and conditional regression tests.

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
are implemented as described in Sections 13.2-13.4.

CBN and CBNeed local bindings remain unsupported by this
CBV-specific rule. CBNeed local bindings will be implemented in B05.6

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

Under CBV, predefined functions use the ordinary `CoreApp`
evaluation path.

The function position is demanded to WHNF before the
argument is evaluated.

The argument is evaluated in the original call-site
environment and explicitly demanded to WHNF.

When applying an unapplied predefined function without
saturating its arity, `CORE_PREDEFINED_PARTIAL_APPLY`:

1. Creates a `PartialPredefinedFunction` retaining the
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

Applying the second argument saturates seq through the
CBV rule described in Section 14.3.

CBN and CBNeed application are not implemented by these
CBV-specific transitions.

### 14.3 Saturated seq Under CBV

A saturated application of the predefined seq function
takes two arguments and returns the reference to its
second argument.

Under CBV, ordinary application rules guarantee that
both arguments reach WHNF before saturation completes.

The first argument has already been demanded when the
`PartialPredefinedFunction` was constructed.

The second argument is demanded by the existing CBV
`ApplyArgumentFrame` before the saturated rule executes.

`CORE_SEQ_SATURATE`:

1. Validates that the function is a supported saturated seq.
2. Verifies that the stored first argument is in WHNF.
3. Uses the already evaluated second argument reference.
4. Removes the application continuation.
5. Restores the caller's lexical environment.
6. Returns the second argument reference.

No additional forcing of the first argument occurs
during CBV saturation.

Saturation does not allocate new heap objects, evaluate
a lambda body, or modify the captured first argument.

This rule is specific to CBV. Under CBN and CBNeed,
seq must explicitly demand its first argument at
saturation because partial application does not force it.

The non-strict operational rules will be implemented
with their corresponding evaluator strategies.

The sequence of operational transitions remains observable
through the existing RuleId and trace infrastructure.

### 14.4 First-Class Integration and Lexical Shadowing

Predefined seq participates in ordinary `CoreApp evaluation`.

The runtime supports:

- Partial applications stored in global or local bindings.
- Passing seq and its partial applications as arguments.
- Applying partial functions through lexical references
  and heap indirections.
- Returning functions from saturated seq applications.
- Applying a function returned by seq.

Predefined function dispatch depends on the runtime heap
object type rather than the source identifier's spelling.

User-defined global bindings, local bindings and function
parameters may shadow the predefined seq identifier.

Shadowed definitions are evaluated as ordinary closures
and must not execute `CORE_SEQ_SATURATE`.

Local bindings containing partial predefined functions
preserve their stable binding addresses and use the
existing Indirection representation.

The frontend does not introduce a dedicated `CoreSeq` node.

## 15. Canonical Result Observation

### 15.1 Passive WHNF Conversion

Canonical observation separates runtime references from
the values exposed as observable program results.

The initial canonical value types are:

- `CanonicalInteger`
- `CanonicalBoolean`
- `OpaqueFunction`

Canonical values do not expose heap addresses, closure
environments or evaluator-specific runtime structures.

`OpaqueFunction` is not used to establish extensional
equality between function values.

`observe_whnf(heap, reference)` converts a reference that
has already reached WHNF into a canonical representation.

It is a passive operation that:

- Does not mutate the heap.
- Does not allocate runtime objects.
- Does not execute Force or EvaluateCore.
- Does not follow unresolved indirections.
- Does not consume evaluator or result-consumer transitions.

References to `Reserved`, `PendingGlobal` or `Indirection` objects
must be resolved by the evaluator before canonical observation.

Unsupported runtime objects must not silently produce
fabricated canonical values.

The canonical value schema will be extended with constructors
when constructor evaluation becomes available in B06.

This subsection defines only passive conversion. ResultPolicy
handling, result-consumer transitions and completion are implemented
separately as described in Sections 15.2-15.5.

### 15.2 WHNF_ONLY Result Consumption

A Core evaluation that reaches a root Return in WHNF is
ready for result observation but is not yet `COMPLETED`.

The initial result consumer supports an explicit
`consume_whnf_result` transition under WHNF_ONLY.

`RESULT_OBSERVE_WHNF`:

1. Validates the requested result policy.
2. Requires a `RUNNING` machine in `EVALUATION` phase.
3. Requires `Return` with an empty continuation stack.
4. Converts the returned reference using passive `observe_whnf`.
5. Records the reference and resolved result mode in `ResultState`.
6. Stores the canonical result separately from `MachineState`.
7. Changes ExecutionStatus to `` COMPLETED .

The transition has kind `RESULT_CONSUMER`.

It increments `stateId` and `transitionIndex` but does not
increment `evaluatorTransitionCount`.

The original control, heap, stack and execution phase
remain unchanged in the successor's machine state.

The previous `ExecutionState` remains independently inspectable.

Result consumption cannot evaluate expressions, force
references, allocate heap objects or perform updates.

A completed result cannot be observed again.

run_batch remains evaluator-only and stops at `WHNF_PENDING`.
The caller may invoke consume_whnf_result explicitly, or use
run_session_batch to coordinate evaluation and consumption
as described in Section 15.5.

`ASK_AT_WHNF` and `MATERIALIZE_COMPLETE_VALUE` are implemented
as described in Sections 15.3 and 15.4.

### 15.3 ASK_AT_WHNF Result Policy

`ASK_AT_WHNF` defers the choice of result-observation mode
until the evaluator reaches a root Return in WHNF.

While awaiting selection:

- `ExecutionStatus` remains `RUNNING`.
- The current control and heap remain unchanged.
- No evaluator or result-consumer transitions occur.
- Repeated `run_batch` calls return `WHNF_PENDING` without progress.

The controller may explicitly select one of:

- `WHNF_ONLY`
- `MATERIALIZE_COMPLETE_VALUE`

`RESULT_SELECT_MODE` records this decision as a
`RESULT_CONSUMER` transition.

The transition:

1. Requires a root `Return` already in WHNF.
2. Records the result reference in `ResultState`.
3. Stores the selected mode in `resolvedResultMode`.
4. Preserves the original `ExecutionConfig`.
5. Leaves the execution `RUNNING`.
6. Does not increment `evaluatorTransitionCount`.

Mode selection is immutable within a run.

When `WHNF_ONLY` is selected, `RESULT_OBSERVE_WHNF`
may complete the execution.

When `MATERIALIZE_COMPLETE_VALUE` is selected,
materialization remains pending until its consumer
is executed.

The selection transition increments stateId and
transitionIndex but does not perform evaluation,
forcing, heap allocation or result materialization.

The unresolved `ASK_AT_WHNF` policy must not be used
directly as an experimental observation outcome.

### 15.4 Atomic Complete-Value Materialization

`MATERIALIZE_COMPLETE_VALUE` requests the complete observable
result rather than only its outermost WHNF representation.

In the current B04 subset, supported results are limited
to integers, booleans and opaque function values.

These values do not require recursive traversal.

`RESULT_MATERIALIZE_ATOMIC` completes such results using
one `RESULT_CONSUMER` transition.

It:

1. Requires an already-WHNF root Return.
2. Validates the configured or explicitly selected mode.
3. Converts the reference into its canonical representation.
4. Records the reference and effective result mode.
5. Changes the phase to `RESULT_MATERIALIZATION`.
6. Sets the execution status to `COMPLETED`.

Atomic materialization does not perform additional
evaluator transitions or heap allocations.

It increments `stateId` and `transitionIndex` but does not
increment `evaluatorTransitionCount`.

The original `ExecutionState` remains unchanged.

A materialized function is represented by `OpaqueFunction`.
No attempt is made to inspect or compare function bodies.

When constructors are introduced in B06, complete-value
materialization will extend this consumer to recursively
demand constructor fields.

Such future demands may require evaluator transitions
under `RESULT_MATERIALIZATION` and must respect both
`executionStepLimit` and `resultNodeLimit`.

The current atomic implementation does not claim
recursive materialization support.

### 15.5 Session Batch Coordination and Limits

`run_session_batch` coordinates Core evaluator execution
and result-consumer transitions.

The existing run_batch function remains evaluator-only
and preserves its established WHNF_PENDING contract.

The session coordinator:

1. Executes a bounded evaluator batch.
2. Detects the WHNF observation boundary.
3. Waits if `ASK_AT_WHNF` has not been resolved.
4. Otherwise invokes the selected result consumer,
   provided the current batch has remaining capacity.
5. Returns the resulting state, trace and stop reason.

`max_steps` limits all transitions performed within one
session batch, including result-consumer transitions.

`executionStepLimit` counts only evaluator transitions.
Administrative result-consumer transitions do not consume
the evaluator budget.

Batch usage is determined using `transitionIndex` differences,
not the number of retained trace entries.

This preserves correct accounting under `METRICS_ONLY`.

An unresolved `ASK_AT_WHNF` selection produces `WHNF_PENDING`
without additional transitions.

If a batch reaches WHNF after exhausting its `max_steps`
budget, result consumption is deferred to a later batch.

For currently supported atomic and opaque values,
complete-value materialization requires one canonical
result node.

The configured `resultNodeLimit` is therefore sufficient
for these results, since its minimum valid value is one.

Recursive materialization, partial materialization and
`RESULT_LIMIT_REACHED` behavior remain pending until
constructor support is implemented.

Full and chunked executions must produce equivalent
canonical results and operational transitions.

For equivalent terminating executions, changing batch
boundaries must not change the canonical result, simulated
allocation accounting or operational transition sequence.

Result-consumer transitions use the session batch capacity
but do not consume the evaluator transition budget.

Consequently, an already-WHNF result may be consumed even
when the evaluator budget is exhausted, provided that the
session batch has remaining transition capacity.

Completed results cannot be consumed again, and result
consumption must preserve previously returned execution
snapshots.

Result consumption does not modify earlier snapshots,
allocate simulated heap objects or alter the evaluation
strategy.
