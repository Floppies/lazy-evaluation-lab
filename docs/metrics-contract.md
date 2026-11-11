
# Instrumentation and Metrics Contract

**Status:** B07 operational contract.
**Scope:** Core CBV and CBNeed instrumentation.

## 1. Purpose and Architectural Principles
- Instrumentation observes but never determines execution.
- Metrics are reduced from explicit transition events and effects.
- Operational rules are independent of metric accounting.

## 2. Transition and Event Accounting
- TransitionKind and ExecutionPhase
- Semantic events versus RuleId
- Event emission and successful-operation boundaries
- Semantic reductions and non-reduction counters

## 3. Source Attribution
- SOURCE, GENERATED and INTERNAL origins
- Desugaring and generated Core constructs
- Curried function applications
- Multiple source origins and no double counting

## 4. Heap and Allocation Accounting
- Allocations and ObjectId identity
- Abstract heap slots
- Initialization baseline
- Current and peak heap usage

## 5. Stack and Phase Accounting
- Push, pop and frame depth
- Peak frame accounting
- Evaluation versus result materialization
- Evaluator and consumer transition counters

## 6. CBNeed Demand and Sharing
- Thunk creation and demands
- Forcing and successful updates
- Sharing and blackholes
- Never-forced thunks and update depth

## 7. Determinism and Comparability
- Snapshot and batching invariants
- Trace mode independence
- Units and comparable configurations
- Partial results and execution limits

## 8. Export Contract
- Versioned run records
- Configuration and provenance
- Metric units and termination status
- JSON and CSV serialization boundaries
