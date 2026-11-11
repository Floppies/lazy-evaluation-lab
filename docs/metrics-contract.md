
# Instrumentation and Metrics Contract

**Status:** Active instrumentation contract.
**Scope:** Core CBV and CBNeed. CBN, STG, garbage
collection, and object-lifetime metrics are outside
the current scope.

## 1. Purpose and Architectural Principles

Instrumentation observes abstract-machine execution without
changing evaluation semantics, demand, allocation, or result
observation.

Metrics are derived from explicit semantic events, heap
effects, stack effects, and transition metadata. A pure reducer
updates the accumulated instrumentation state.

`RuleId` identifies operational transitions; it is not a
metric event and must not be interpreted by the reducer to
infer semantic reductions.

The accounting contract is independent of trace retention.
Metrics must remain consistent across FULL, EVENTS, and
METRICS_ONLY trace modes.

Accumulated metrics are stored in an immutable
`InstrumentationState` attached to each `ExecutionState`.
Scalar counters are grouped in `MetricCounters`, while
run-level accounting metadata, such as the initialization
heap baseline, belongs to `InstrumentationState`.

Derived metrics are not stored redundantly:
`semanticReductions` is the sum of the six semantic
reduction counters, `currentFrames` equals pushes minus
pops, and `thunksNeverForced` equals created thunks minus
thunks whose evaluation has started. These identities rely
on the event-accounting invariants defined below.

Instrumentation updates produce new immutable values.
Historical snapshots may safely share unchanged metric
objects. Per-object lifecycle tracking and detailed metric
breakdowns will be introduced only when their corresponding
accounting rules are implemented.

## 2. Transition and Event Accounting

`TransitionKind` and `ExecutionPhase` are independent
dimensions. The former identifies the component performing
work; the latter identifies the execution phase.

Semantic events represent actual operations rather than
preparatory transitions. Failed operations do not emit
successful-reduction events.

The supported Core semantic events are:

- `FUNCTION_APPLIED`: a successful unary application,
  including applications of first-class predefined functions.
- `BETA_REDUCED`: entry into a closure body following an
  effective unary application.
- `LET_ACTIVATED`: activation of a Let or LetRec group,
  counted once per activation rather than per binding.
- `PRIMITIVE_REDUCED`: successful primitive evaluation,
  including unary negation.
- `CONDITIONAL_SELECTED`: successful if-branch selection.
- `CASE_ALTERNATIVE_SELECTED`: successful case-alternative
  selection, not subsequent entry into the selected body.
- `SEQ_REDUCED`: continuation with the second argument
  after the first argument reaches WHNF.
- `VARIABLE_LOOKED_UP`: actual evaluation of a CoreVar,
  excluding internal environment inspections.

The six reduction counters define:

    semanticReductions =
        betaReductions
        + letReductions
        + primitiveReductions
        + conditionalReductions
        + caseReductions
        + seqReductions

`functionApplications` and `betaReductions` can describe
the same effective closure application. They are separate
measurements and must not both contribute to
`semanticReductions`.

A first-class `seq` application may be partially applied.
The first successful unary application counts as
`FUNCTION_APPLIED`, but not as `BETA_REDUCED` or
`SEQ_REDUCED`. A successful second unary application also
counts as `FUNCTION_APPLIED`; the `SEQ_REDUCED` event occurs
only after the first argument reaches WHNF and execution
continues with the second argument. Failed applications
do not produce successful-application events.

One semantic event contributes once to its corresponding
global counter, regardless of the number of source locations
associated with it.

### Typed Transition Payloads

`TransitionResult` carries four optional, immutable
instrumentation payloads:

- `semantic_events`: a tuple of `SemanticEvent` values.
- `heap_effects`: a tuple of `HeapEffect` values.
- `stack_effects`: a tuple of `StackEffect` values.
- `source_origins`: a tuple of `EventOrigin` values.

Each semantic event carries its own provenance. The
transition-level `source_origins` field provides contextual
attribution and must not independently increment or duplicate
metric counters.

All payloads default to empty tuples. This preserves
compatibility with existing transition producers while
instrumentation emitters are introduced incrementally.

`TraceEntry` remains a compact operational trace record.
Metric accounting consumes the original transition data
independently of trace retention or presentation mode.

Typed payloads describe observed operations; their presence
must not influence evaluation, demand, allocation, or
execution limits.

### Pure Metrics Reduction

`reduce_metrics(previous, transition)` returns a new immutable
instrumentation state. It reads the transition's explicit
metadata and semantic events without modifying the transition,
the abstract machine, or the previous instrumentation state.

Evaluator transitions increment `evaluatorTransitions`.
Evaluator transitions whose `phase_before` is
`RESULT_MATERIALIZATION` additionally increment
`resultDemandEvaluatorTransitions`. Result-consumer
transitions increment `resultConsumerTransitions`.

Each supported Core semantic event increments its corresponding
counter exactly once per occurrence. `semanticReductions` remains
a derived value and is never incremented directly.
Source attribution does not alter global event counts.

The pure reducer accounts for transition metadata, Core
semantic events, heap and stack effects, initialization
baseline recording, and CBNeed lifecycle events.

A per-transition `SemanticEventRecorder` collects events
emitted by evaluator rules and transfers them to the
immutable `TransitionResult.semantic_events` payload.

Supported Core evaluation emits events for successful
function applications, beta reductions, local let activation,
primitive execution, conditional selection, case-alternative
selection, saturated `seq` reductions, and variable lookups.

Events are emitted at successful operational boundaries.
Preparing a continuation, demanding an operand, or entering
an already selected case body does not independently count
as a successful semantic reduction.

Heap and stack effect types and their reducer accounting
are implemented, but emission of those effects by the
runtime is not yet integrated. CBNeed lifecycle event
emission and per-anchor lifecycle validation also remain
pending.

`ExecutionState` carries an `InstrumentationState`, but
evaluator execution does not yet update its accumulated
metric counters. Result-node accounting and pending
thunk-chain depth tracking are likewise not yet integrated.

## 3. Source Attribution

Every semantic event may carry an `EventOrigin` containing
an origin kind and zero or more `SourceSpan` values.

The supported origin kinds are:

- `SOURCE`: work attributable directly to source syntax.
- `GENERATED`: work introduced by desugaring or lowering.
- `INTERNAL`: work belonging to runtime infrastructure.
- `UNKNOWN`: insufficient provenance information.

`UNKNOWN` must not be silently converted into `SOURCE`
or `INTERNAL`. In particular, directly constructed Core
programs may lack source-level provenance.

A source span alone does not establish whether a Core node
was generated. Desugaring may produce several nodes sharing
a span. Provenance must therefore be represented explicitly
where attribution is required.

Core nodes carry an immutable, keyword-only `origin` metadata
field using the shared `OriginKind` enumeration defined in
`lazy_lab.source`. The field defaults to `UNKNOWN` and is
excluded from structural equality, just like `SourceSpan`.

The Core representation does not depend on the metrics
package. Semantic event producers convert Core provenance
into `EventOrigin` values when recording actual operations.

Surface-to-Core desugaring assigns explicit provenance to
the Core structures it creates. Source-authored literals,
variables, applications, primitive operations, conditionals,
recursive bindings, and explicitly declared function
parameters receive `SOURCE`.

Constructor chains introduced for list literals receive
`GENERATED`, as do auxiliary cases, alternatives, parameter
bindings, and temporary lambdas introduced by pattern
matching. The original equation bodies retain `SOURCE`
provenance.

The per-transition `SemanticEventRecorder` converts the
origin and optional source span of a Core node into an
`EventOrigin` attached to the emitted semantic event.

Successful application events are attributed to their
originating `CoreApp`. Beta reductions are attributed to
the `CoreLam` whose body is entered. A saturated `seq`
reduction retains the provenance of its saturating
application.

Variable lookups are attributed to their evaluated
`CoreVar`, local recursive-binding activations to their
`CoreLetRec`, and primitive reductions to the originating
`CorePrimOp`.

Continuation frames and the `ApplyPrimitive` control
preserve the relevant Core node when evaluation requires
intermediate steps. This avoids losing attribution while
operands are evaluated or references are demanded.

Conditional-selection events retain the provenance of
their originating `CoreIf`. Case-selection events retain
the provenance of their originating `CoreCase`, including
`GENERATED` for case expressions introduced by pattern
matching. Both are preserved across their corresponding
continuation frames.

CoreCase expressions introduced to implement source-level
pattern matching contribute to `caseReductions` when their
alternatives are selected. Their origin is `GENERATED`;
they must not be presented as case expressions explicitly
written by the user.

Likewise, generated CoreLetRec expressions contribute real
Core work but retain their generated provenance.

Curried functions are accounted for according to effective
unary Core applications. For example, evaluating
`add 2 3` may enter two nested closure bodies and therefore
produce two beta reductions, even though the source appears
to contain a single function call.

Source-level attribution does not change Core operational
totals. Multiple source spans associated with an event must
not duplicate that event in the global counters.

## 4. Heap and Allocation Accounting

Heap usage is measured in abstract slots, not native bytes.

`HeapAllocated` records creation of a new ObjectId, the
allocated slot count, the initial object type, and optional
provenance. Each successful allocation contributes exactly
once to `totalAllocations`.

`HeapReplaced` records a change to an existing cell without
creating another ObjectId or increasing its reserved capacity.
Replacing a reservation or updating a thunk is not, by itself,
a new allocation.

Logical thunk creation is distinct from heap allocation.
Installing a thunk in a previously reserved anchor may
produce `THUNK_CREATED` without another allocation of that
anchor. Separately allocated payload cells remain allocations.

`HeapBaselineRecorded` captures the slot count at the end
of global initialization, before entry-expression evaluation.
It does not modify the heap.

The accounting invariants are:

    currentHeapSlots =
        sum(cell.allocated_slots for cell in heap.cells.values())

    peakHeapSlots =
        max(currentHeapSlots across observed execution states)

    additionalPeakOverBaseline =
        max(0, peakHeapSlots - baselineSlots)

The metrics reducer processes heap effects in their recorded
operational order. Each `HeapAllocated` effect increments
`totalAllocations` and increases `currentHeapSlots` by its
reserved slot count. `peakHeapSlots` is updated after each
allocation. `HeapReplaced` preserves allocation and slot
totals. `HeapBaselineRecorded` establishes the initialization
baseline exactly once and does not modify the heap counters.

The absolute peak includes initialization and result
materialization. No garbage collection or physical-memory
measurement is implied by these abstract counters.

## 5. Stack and Phase Accounting

Only explicit abstract-machine continuation frames are
counted. Python interpreter call-stack frames are excluded.

`StackPushed` and `StackPopped` represent individual
successful stack operations, retaining their operational
order and frame type.

The accounting invariants, for an initially empty stack, are:

    currentFrames = pushes - pops
    peakFrames = max(currentFrames across the execution)

The reducer processes stack effects sequentially.
`StackPushed` increments pushes and updates the peak after
the operation; `StackPopped` increments pops. Pops that
would produce a negative accounted depth are rejected.
Intermediate stack depths are preserved for peak accounting,
even when the net depth change of a transition is zero.

`evaluatorTransitions` counts every transition whose kind
is EVALUATOR, including global initialization and evaluation
triggered by result materialization.

`resultDemandEvaluatorTransitions` is the subset of evaluator
transitions performed during RESULT_MATERIALIZATION.
It must not be added again to `evaluatorTransitions`.

`resultConsumerTransitions` separately counts transitions
whose kind is RESULT_CONSUMER.

Result materialization can demand additional evaluation,
allocate heap objects, and increase stack and semantic-work
metrics. Merely reading metrics, replaying a snapshot, or
inspecting the trace does not demand evaluation.

Phase-boundary events must be recorded explicitly where
necessary. The reducer must not infer metric events merely
from a change in phase or from a particular RuleId.

## 6. CBNeed Demand and Sharing

The pure reducer supports the six CBNeed lifecycle event
categories defined below. Runtime emission of these events,
per-anchor lifecycle validation, sharing attribution, and
pending update-chain depth accounting are not yet integrated.

The supported event types already include thunk creation,
demand, first force, successful update, shared-result reuse,
and blackhole detection.

Thunk identity follows the stable anchor, not an
intermediate payload address. The definitions in technical
specification section 10 remain authoritative.

### CBNeed Event Accounting

The metrics reducer recognizes six explicit CBNeed lifecycle
events: `THUNK_CREATED`, `THUNK_DEMANDED`, `THUNK_FORCE_STARTED`,
`THUNK_UPDATED`, `SHARED_RESULT_HIT`, and
`BLACKHOLE_DETECTED`.

Each event increments only its corresponding counter.
A demand does not implicitly count as a force, an update,
or a shared-result hit. Likewise, a successful update does
not imply a new allocation.

`thunksNeverForced` is derived as `thunksCreated` minus
`thunksForced`, relying on each thunk being created and
first-forced at most once in the corresponding accounting
categories.

Lifecycle events identify the stable thunk anchor through
its `ObjectId`. Per-anchor lifecycle validation and pending
update-chain depth tracking remain outside the current
runtime integration.

The reducer does not infer lifecycle events from `RuleId`,
heap object types, or changes in the heap state.

## 7. Determinism and Comparability

Instrumentation must not alter evaluation strategy,
execution budgets, demand, or observable program results.

Equivalent executions using different batch sizes or trace
modes must produce equivalent accumulated metrics. Historical
snapshots must preserve their own metric values.

Metric comparisons identify the measured quantity, unit,
included phases, evaluation strategy, result policy, and
relevant execution limits.

A ratio is reported only when its denominator is positive
and the runs satisfy the required comparability conditions.
An unavailable ratio must not be replaced with an invented
value.

Step-limited and result-limited executions yield truncated
measurements. Such measurements may be reported with their
termination status but must not be presented as complete
execution costs.

Abstract slots, semantic reductions, and continuation frames
must not be equated with native memory bytes, machine
instructions, or physical stack usage.

### Reducer Accounting Invariants

The reducer processes each transition exactly once and
returns a new immutable instrumentation state.

Heap allocations require positive integer slot counts.
The initialization baseline may be recorded only once and
must match the accounted current heap slots at that point.
This assumes that the initial heap was empty or correctly
represented in the initial instrumentation state.

Stack pops must not produce a negative accounted frame depth.
Peak heap usage and peak stack depth are monotonic across
successive instrumentation states.

Applying the same ordered transition sequence in different
batch partitions must produce identical accumulated metrics.
These are reducer-level guarantees; end-to-end batch and
snapshot equivalence is validated after producer integration.

## 8. Export Contract

Versioned run records and JSON/CSV export are not yet
implemented. Their design must preserve the metric
definitions, comparison metadata, and partial-execution
semantics specified in Section 7.
