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