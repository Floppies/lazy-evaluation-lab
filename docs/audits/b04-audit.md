# B04 Audit: Core Call-by-Value Evaluation and Canonical Observation

Date: 2026-10-27. Branch: `feature/core-evaluator`.
Audited HEAD: `f44b395f44cf3e7af7740a17debc32fdb0beb2d2`.

## 1. Executive Summary

**Decision: ACCEPTED WITH LIMITATIONS.** No reproducible correctness defect in a valid program of the supported B04 subset, or current architectural obstacle to B05, was found. One **Low / Confirmed / Open** finding concerns inaccurate current documentation status and navigation. It does not require a language-semantics change or block Call by Need development.

The initial checkout was clean. The baseline complete suite passed **1,618 tests**. This audit adds three test functions, comprising **five collected instances**, for terminating mutual recursion with exact captures and shadowing, failure atomicity after partial local initialization, and deep interrupted execution. Final complete verification passed **1,623 tests, zero failures**. Production code, existing tests, specifications, ADRs and historical audits were not changed. No commit or branch change was made.

The acceptance rests on implementation and contract review, deterministic source-program probes, transition/snapshot checks, deep validated Core execution and measured branch coverage, as well as pytest. Passing tests alone are not a proof of semantic correctness. Repository coverage is **96.44% executable lines / 90.59% branch outcomes**; runtime plus engine is **93.82% / 83.73%**. Remaining coverage gaps and construction assumptions are described below.

This decision covers the first Core CBV evaluator and its current canonical observation interface. It does not establish CBNeed/CBN correctness, cross-strategy equivalence, final trace persistence, or experimental validity.

## 2. Scope and Methodology

### Checkout and environment

- Current local source was reviewed; no older branch, remote checkout or historical test result substituted for it. HEAD remained unchanged during verification.
- Environment: Windows 11, repository `.venv/Scripts/python.exe`, Python **3.14.3**, pytest **9.1.1**, pytest-cov **7.1.0**, coverage **7.16.2**. These versions were read locally. No dependencies were installed.
- Review covered every runtime module; `engine/core_machine.py`, `result_consumer.py` and `session_runner.py`; the compilation pipeline, free-variable analysis and pertinent lowering/name-resolution boundaries; existing runtime, integration, audit, Core and semantics tests.
- Independent review tracks examined operational semantics, observation/batches, and documentation/inherited findings. Their conclusions were reconciled against the same checkout before this report was written.

### Authority and planning

Sources included [the evaluation contract](../core-evaluation-contract.md), [language specification](../specifications/language-specification.md), [technical specification](../specifications/technical-specification.md), [milestones](../planning/milestones.md), `docs/planning/gantt.xlsx`, ADR-001/003/004/005/006, [B03 audit including its follow-up](b03-audit.md), and [B02.8 audit](b02.8-audit.md). Runtime/Core module guides were checked for implementation claims. Auxiliary construction notes were treated as non-authoritative historical material; the supplied `vore-evaluator-construction.md` name is a typo for the local `core-evaluator-construction.md` reference.

The Gantt was inspected read-only through ZIP/XML. Sheet `Gantt B`, rows 16 and 39, defines B04 as CBV and the first evaluator plus canonical observation/demand modes; it allocates 20 planned hours. Rows 40-41 place thunk/update/sharing/blackhole infrastructure and executable constructors/case in B05-B06. It contains no separate B04.1-B04.8 acceptance cells. The current contract supplies the operational detail.

Technical specification **section 16 is an accepted additive v2.0 revision**. Its section 16.1 explicitly gives revised decisions precedence over the retained v1.1 text. In particular, name-based lexical environments, ordinary optional `main`, one recursive `let`, on-demand globals and first-class curried `seq` are accepted revisions. Historical SymbolId, special-main, sequential-let and nonpartial-seq passages are not automatically runtime defects. This audit neither reverses those decisions nor rewrites their history.

### Verification approach

Review traced each continuation from scheduling through demand and consumption, and checked reference/environment identity and allocation capacity at those boundaries. Programs with expected runtime errors or bounded recursive divergence were separated from incorrect results. Manually forged state graphs and mutable extension classes were not treated as valid compiled programs: the B03 follow-up expressly accepts trusted typed internal construction.

New tests were restricted to critical properties with insufficient execution coverage. Existing B04.6-B04.8 tests, including the result-mode string regression, were retained unchanged. There are no skips, expected-failure markers, weakened existing assertions, production fixes or newly failing defect regressions in this patch.

## 3. Specification and ADR Compliance

All implementation paths below are relative to `src/lazy_lab/`.

| Component | Implemented behavior and governing contract | Evidence and boundary |
| --- | --- | --- |
| Evaluation/demand | `EvaluateCore` evaluates syntax, `Return` delivers a reference, `Force` requests WHNF. Contract sections 1, 7.7, 8.2 and 11. | `engine/core_machine.py:136,690,711,792`; existing Core-runtime tests distinguish lookup from forcing. |
| Globals/entry | Reserve predefined and user scopes, install all RHS representations, then enter the selected expression. Globals activate on demand, including under CBV. Contract sections 7.2, 8.3-8.4, 9; technical section 16.4. | `core_machine.py:387,437,496,1053`; initialization tests cover forward references, shadowing, selected entries and allocation. |
| Closures/application | Definition-site free-local references, parameter-over-captures-over-globals lookup, curried left-to-right strict arguments. ADR-005; technical section 16.3; contract sections 10-11. | `runtime/closures.py:78`, `core/free_variables.py:25`, `core_machine.py:1124,1187,1317`; nested/returned closure and shadowing tests. |
| Recursive locals | Mutually recursive visibility, stable one-slot anchors, separately allocated closures, source-ordered strict RHS initialization. ADR-001/006; contract section 13. | `core_machine.py:592,1464,1522`; local initialization tests and new terminating mutual-recursion regression. Visibility does not promise an initialized forward value. |
| Primitives/if | Strict left-to-right operands, explicit arity/type checks, one selected conditional branch. Contract section 12. | `core_machine.py:915,1334,1407`; existing arithmetic/comparison, invalid-type and selective-branch tests. |
| `seq` | Ordinary first-class predefined value; partial application is WHNF; CBV saturates after both arguments reach WHNF and returns the second reference. B02.E, language section 4.6, technical section 16.5, contract section 14. | `runtime/predefined.py`, `core_machine.py:1187`; existing first-class, strictness, shadowing, reference-identity and batch tests. |
| Observation | Passive canonical conversion, fixed WHNF/materialization policies and explicit ASK selection. Contract section 15. | `runtime/observation.py:53`, `engine/result_consumer.py`; supported results are integers, booleans and opaque functions. |
| Batches/tracing | Evaluator-only `run_batch`; session coordination counts all batch transitions, with separate evaluator budget. Contract sections 8 and 15.5. | `core_machine.py:359,1011`, `engine/session_runner.py:29`; existing exact-limit/trace tests and supplementary split-point checks. |
| Static boundary | Check all Surface names before pruning, then validate/check resulting Core. ADR-004. Runtime does not replace these passes. | `pipeline.py:15`; semantics/audit tests retain unknown-name rejection, including discarded equations and unselected branches. |

ADR-003's iterative-traversal obligation is respected by the reviewed analysis, lookup and operational stepping. No Python recursion-limit increase was used. ADR-006's anchor overhead is implemented and explicitly recognized as representation cost; it is not a source-reduction metric.

## 4. Semantic Correctness Assessment

### Evaluation order, WHNF and identity

`CoreApp` first preserves the argument and call-site environment in `ApplyFunctionFrame`, evaluates the function, and explicitly forces its returned reference. Under CBV it then evaluates and forces the argument before either entering a closure body or dispatching a predefined function. An `awaiting_whnf` flag distinguishes evaluation return from completed demand. Nested applications preserve the surrounding continuation rather than using recursive Python evaluation.

Variable evaluation returns the environment's existing reference without forcing it. `Force` follows each `Indirection` in its own transition, returns immediate/function WHNF references, and activates `PendingGlobal` in the global environment with a return continuation. Root `WHNF_PENDING` now requires an empty stack and a recognized WHNF reference; it does not mean merely that a `Return` exists. Recognized B04 forms are integer/boolean immediates, closures, unapplied predefined functions and partial predefined functions. Constructors/case remain explicitly unsupported.

Global aliases are not memoized or path-compressed. Repeated demands may reevaluate a non-lambda global RHS; that is the current B04 contract, not an accidental CBNeed implementation. Lambda globals are already installed function objects. Returned closures and partial predefined values retain existing references through aliases and local anchors.

### Scope, capture and recursion

`free_variable_names()` uses explicit scope counters, including recursive `let` groups and alternative-local binders. Capture selection inspects lexical scopes above the global boundary, deduplicates/sorts names, and obtains the nearest definition-site reference. Globals and predefined names are not unnecessarily captured. An outer closure includes references needed by a nested lambda without executing its body.

The new source regression is:

```haskell
bias = 100
main = let { bias = 7; even n = if n == 0 then bias else odd (n - 1); odd n = if n == 0 then 0 else even (n - 1); alias = even } in (\bias -> alias 4) 99
```

Expected and observed result: **7**, with **199 evaluator transitions**, an empty stack and restored global environment. The test verifies exact capture sets `even={bias, odd}`, `odd={even}` and caller `{alias}`; recursive captures use original binding anchors and the alias points to the same closure reference. This exercises actual terminating calls across the recursive cycle, beyond installation-only examples.

Local binding initialization reserves every name before RHS evaluation, but initializes in source order. `let { x = y; y = 10 } in x`, self-demand and a demand on a later uninitialized lambda are specified `UninitializedLocalBindingError` cases under section 13.4. Their lexical visibility does not establish value availability. They must not be misreported as broken mutual scope. Function bodies may retain later references without demanding them; the reviewed terminating recursive example succeeds once initialization has completed.

### Primitives, conditionals and `seq`

Arithmetic/ordering/negation require integer immediates. Equality/inequality require two values of the same supported primitive type; Python's boolean-as-integer relationship does not admit mixed integer/boolean equality. Unsupported operators/arities produce explicit errors. Literals and primitive operations do not allocate simulated heap objects. Conditional selection demands a boolean and evaluates only the chosen branch; an ill-typed unselected branch is not executed, although static name visibility still applies.

Predefined dispatch uses heap-object type, not a Core variable's spelling. Global, local and parameter bindings named `seq` therefore execute ordinary user functions. CBV partial application forces its first argument before constructing a two-slot partial value. Saturation checks the stored WHNF invariant, does not force that argument again, and returns the already evaluated second reference without allocation. Existing tests exercise closures and partial functions as arguments/results, later application, indirections, strict divergence and absence of repeated global demand. Additional read-only probes confirmed `seq` returning a partial `seq`, then applying it.

No supported-program mismatch was reproduced in these areas. Bounded recursive nontermination is not a proof of divergence, and a specified runtime type/initialization error is not an evaluator defect.

## 5. Runtime State and Snapshot Invariants

Public `step()` validates configuration/status/control/budget, clones mutable heap/stack storage through `ExecutionState.snapshot()`, applies one rule to the successor, then advances IDs and evaluator count. Built-in payloads, environments and frames are immutable. Heap replacement preserves address and allocated capacity; immediate values allocate no heap cell. Global cells and local anchor/closure allocations match their declared abstract sizes.

Restore continuations return application bodies and `let` bodies to the enclosing environment. Function/argument/global-demand/local-initialization frames remain pending during nested work and are consumed exactly once. Existing seq/letrec tests and the new deep/mutual-recursion cases verify empty terminal stacks and identity restoration to the global environment.

### Failure after partial initialization

New test `test_error_after_partial_letrec_initialization_preserves_snapshot` compiles:

```haskell
main = let { x = 10; good y = x + y; bad = good True } in good 1
```

Expected and observed: a primitive `TypeError` at `ApplyPrimitive("+", (10, True))`. At that point `x` is initialized, `good` has a closure capturing the original `x` anchor, and `bad` remains `Reserved`. Repeating the failing `step()` and a one-step session batch leaves cells, slots, IDs, counts, frames, control, result state and lexical environments unchanged. The error itself is correct; this passing test checks transition atomicity after earlier successful work. A multi-transition batch is not a transaction rolling back all earlier transitions; the invariant applies to each supplied state and failed transition.

### Deep valid execution and resumption

The new parametrized deep test builds finite, acyclic Core programs and runs both Core validation and name checking before initialization. Depth is **1,200**, above this environment's default Python recursion limit. Comparisons avoid recursive AST dataclass equality/repr.

| Program shape | Expected/observed canonical result | Total evaluator transitions | Observation transitions | Final heap slots |
| --- | --- | --- | --- | --- |
| Nested identity applications | 42 | 12,010 | 1 | 1,202 |
| Nested shadowing local scopes | 0, from the innermost binding | 9,611 | 1 | 1,202 |
| Forward global alias chain | 42 | 6,015 | 1 | 1,203 |

Each shape completes directly and after pausing inside active continuations, with equal counters/slot accounting, zero final frames and restored globals. Paused and initial snapshots remain unchanged. METRICS_ONLY retains no trace entries and does not change step accounting. These are bounded robustness checks, not a complexity benchmark or a claim about arbitrary host-memory limits.

### Inherited B03/B02.8 findings

| Prior finding | Current disposition |
| --- | --- |
| B03 F01: allocation capacity validation order | **Fixed before this audit; correction verified again.** `heap.py:85-94` validates an exact positive integer before comparison. Retained nonnumeric-capacity regressions pass in current verification. |
| B03 F02/F03: extension mutability/manual invalid states | Trusted typed-construction preconditions were expressly accepted in the B03 post-audit follow-up. Arbitrary mutable subclasses or forged child values are not newly discovered valid-program B04 bugs. External state import needs deliberate validation at its future boundary. |
| B03 F04: conflicting original specifications | Substantive decisions reconciled by technical section 16, current language rules and accepted ADRs. Current-status/link drift persists as B04 F01 below. |
| B03 F05 / B02.8 F03: aliases, recursive bindings, demand | Supported CBV behavior now executes and is tested. Nonmemoizing CBN, shared CBNeed updates and executable matching remain future verification obligations. |
| B02.8 F05/F06 | Manual AST scalar-subclass contracts and deep dataclass equality/repr/hash remain inherited input/tooling limits. No evaluator failure caused by them was reproduced here. |
| B02.8 F07 | Source-work attribution remains a B07/experimental-design obligation. Raw evaluator transitions and administrative anchors cannot automatically count as source reductions. |

## 6. Result Observation and Batch Execution

`observe_whnf()` performs passive conversion only. Integer/boolean immediates yield matching canonical scalars; all supported function categories yield an empty-field `OpaqueFunction`, without exposing addresses, captures or runtime references. Opaque functions do not establish extensional equality: tests compare their category rather than independent opaque objects for equality. `Reserved`, `PendingGlobal` and unresolved `Indirection` are rejected without forcing or mutation.

`WHNF_ONLY` consumes an already-WHNF root result. `ASK_AT_WHNF` waits without transitions, then records one explicit selection in a successor `ResultState`, preserving `ExecutionConfig`. A second choice on that selected state is rejected. `MATERIALIZE_COMPLETE_VALUE`, fixed or selected, supports current atomic/opaque values in one result-consumer transition and uses `RESULT_MATERIALIZATION` phase. All supported complete results require one canonical node, so `result_node_limit=1` is sufficient. Canonical values are stored separately from `MachineState`; internal `ResultState` retains the result reference.

The previously repaired string-selection bug remains covered by `test_ask_at_whnf_rejects_invalid_selection`: both `"WHNF_ONLY"` and `"MATERIALIZE_COMPLETE_VALUE"` are rejected as non-`ResultPolicy` inputs. No further correction was needed.

Each successful consumer/selection transition advances `state_id` and `transition_index` without incrementing `evaluator_transition_count`. An already-WHNF result can be consumed after the evaluator budget is exhausted. `run_batch()` remains evaluator-only. `run_session_batch()` uses index differences, not trace length, to enforce a total batch-transition limit; it defers consumption when no capacity remains. Unresolved ASK waits at `WHNF_PENDING`, and completed inputs return unchanged at `TERMINAL_STATUS` without new entries.

Existing integration tests verify exact evaluator limits, one-step ASK selection/completion, minimum node limits, immutable snapshots, final non-resumption, and all trace modes. FULL and EVENTS currently retain the same basic transition records; METRICS_ONLY retains none. This is the documented basic tracing boundary, not full B08 history/replay support.

A supplementary read-only matrix tested **2,334 two-batch split-point comparisons** over eight valid programs, both fixed policies and all three trace modes. Each baseline completed run was cut at every transition before completion, then resumed. Results/categories, concatenated traces, evaluator/total counts, result modes and paused snapshot contents agreed. This is supplementary deterministic probe evidence, not 2,334 extra pytest cases or a formal equivalence proof.

## 7. Findings

### B04 F01 — Current implementation-status prose and navigation are stale

- **Severity:** Low.
- **Status:** **Confirmed / Open**. No documentation correction was applied in this audit.
- **Affected locations:** `docs/core-evaluation-contract.md:3,61,597,763,825,908,1645`; `docs/decisions/ADR-005-lexical-runtime-environments.md:3`; `docs/core-ir.md:7`; `src/lazy_lab/engine/core_machine.py:1` module docstring. The incremental contract paragraphs do not consistently label their limitations as historical submilestone boundaries. `docs/runtime.md` is explicitly B03-oriented and should be labeled/navigated accordingly rather than interpreted as the primary B04 contract.
- **Minimal documentary reproduction:** Read the contract header (`B04.1 draft`) and section 4's caveat that `WHNF_PENDING` does not guarantee WHNF; compare `_stop_reason()` at `core_machine.py:359-375`, which explicitly checks WHNF. Read sections 9.6/10.6/11.4/11.7/15.2 alongside their implemented later sections and the operational modules. ADR-005 still says implementation pending; Core IR overview says runtime evaluation is future work; the evaluator module describes only literal transitions. Running the current Core-runtime/result-consumer suites demonstrates the broader implemented boundary.
- **Expected:** Current top-level status and cross-references accurately identify completed CBV/observation support; old subsection limitations identify the submilestone to which they applied.
- **Observed:** The same current documentation mixes initial-stage limitations with completed B04.4-B04.8 contracts. It can incorrectly imply no forcing, application, WHNF certification or canonical completion exists.
- **Related reproducible navigation defect:** ADR-001/004/005 line 6 link to absent `docs/language-specification.md`. Language specification line 793 resolves `decisions/ADR-004-...` and `name-resolution.md` under its own directory, where they do not exist. `Test-Path` returned false for each corresponding target. These are existing broken relative links, not missing semantic implementations.
- **Contract affected:** Repository documentation-authority and implementation-status accuracy requirements. Technical section 16.7 also explicitly calls for current references/status to be reconciled without rewriting history.
- **Impact:** Reader/handoff ambiguity, especially when implementing B05 from older-looking boundaries. No incorrect result, heap mutation, broken accepted lexical rule or B05 architectural block was observed.
- **Minimal proposed correction:** Update current status/overview text and ADR-005's implementation note, qualify incremental historical boundaries, and repair relative links. Preserve the original decisions and dated audit evidence; no new semantic ADR is needed. Estimated work: **1-2 hours including review/link checks**.

Finding counts: **Critical 0; High 0; Medium 0; Low 1; Informational 0**. Inherited accepted preconditions and explicitly deferred milestone work are tracked separately below, not inflated into new defects. No unverified hypothesis is classified as a confirmed runtime defect, and no new issue is marked Fixed.

## 8. Test Evidence and Coverage

### Added tests

| New file under `tests/audits/` | Collected instances | Purpose |
| --- | --- | --- |
| `test_b04_semantic_regressions.py` | 1 | Terminating mutual local recursion, exact captures, aliases, definition-site shadowing and original anchors. |
| `test_b04_observation_regressions.py` | 1 | Atomic expected error after partial strict local initialization, through direct and session APIs. |
| `test_b04_execution_regressions.py` | 3 | Deep applications, scopes and global chains; interrupted/direct execution equivalence and snapshot/slot/frame invariants. |

These target previously under-tested combinations, rather than duplicating first-class seq, ASK/string validation or ordinary shallow closure tests. No production bug was exposed by the added tests. Coverage percentages remain unchanged from baseline: the added evidence strengthens operational properties and depth, rather than merely reaching new lines.

### Commands and observed outcomes

Commands ran from the repository root. Durations are pytest host execution times, not evaluation-cost measurements.

| Command | Observed outcome |
| --- | --- |
| `.venv/Scripts/python.exe -m pytest -q` before additions | **1,618 passed**, 2.45s; one existing cache warning. |
| `.venv/Scripts/python.exe -m pytest -q --cov=lazy_lab --cov-branch --cov-report=term-missing` before additions | **1,618 passed**, 2.66s; one existing cache warning; baseline coverage measured. |
| `.venv/Scripts/python.exe -m pytest tests/audits/test_b04_execution_regressions.py tests/audits/test_b04_semantic_regressions.py tests/audits/test_b04_observation_regressions.py -q -p no:cacheprovider` | **5 passed**, 1.12s. |
| `.venv/Scripts/python.exe -m pytest tests/runtime tests/integration tests/audits tests/core tests/semantics -q -p no:cacheprovider` | **732 passed**, 2.42s. |
| `.venv/Scripts/python.exe -m pytest tests/ast tests/frontend tests/core -q -p no:cacheprovider` | **1,020 passed**, 1.16s. |
| `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider` | **1,623 passed**, 3.21s. |
| `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider --cov=lazy_lab --cov-branch --cov-report=term-missing` | **1,623 passed**, 3.60s; final coverage measured. |
| `git diff --check` | Exit 0; no whitespace errors in tracked changes. |
| `git diff --exit-code -- src docs/core-evaluation-contract.md docs/specifications docs/decisions tests/runtime tests/integration` | Exit 0; these existing production/contract/test paths are unchanged. |
| `git diff --no-index --check -- /dev/null <new-file>` for this report and each new test file | Exit 1 for new-file differences; only Git's LF-to-CRLF notices, no whitespace-error diagnostics. |

All final pytest commands exited zero. Focused groups overlap and must not be added together as independent test counts. Five new cases account for the complete-suite increase from 1,618 to 1,623.

An initial new deep test paused the global-chain case just after installing its many globals, then incorrectly expected an active demand frame. The test setup was corrected to pause later inside the chain; the frame assertion remains in place. That intermediate result was **4 passed / 1 failed**, a test-construction error rather than an implementation defect. An exploratory deep probe also initially used an incorrect name-checker import; it was corrected to `check_core_names` before any execution result was reported.

The existing optional pytest cache produced `PytestCacheWarning` (`WinError 183`). Final runs disabled only the cache provider, without changing tests. An optional coverage JSON export under `.pytest_cache/b04-audit` failed with `PermissionError`; no cache repair was attempted. Exact coverage totals were instead obtained read-only by loading `.coverage`, rendering coverage JSON to an in-memory stdout buffer and aggregating its summaries. No temporary JSON/coverage artifact is included in the patch.

### Measured coverage

The `Cover` column of pytest-cov's branch report combines lines and branch outcomes; it must not be quoted as line coverage alone.

| Scope | Executable lines | Branch outcomes | Combined |
| --- | --- | --- | --- |
| Entire `lazy_lab` | 2,329 / 2,415 = **96.44%** | 857 / 946 = **90.59%** | **94.79%** |
| Runtime plus engine | 1,033 / 1,101 = **93.82%** | 355 / 424 = **83.73%** | **91.02%** |
| `engine/core_machine.py` | 390 / 435 = **89.66%** | 213 / 260 = **81.92%** | **86.76%** |
| `engine/result_consumer.py` | 65 / 78 = **83.33%** | 31 / 44 = **70.45%** | **78.69%** |
| `engine/session_runner.py` | 29 / 31 = **93.55%** | 14 / 16 = **87.50%** | **91.49%** |
| `core/free_variables.py` | 72 / 75 = **96.00%** | 45 / 48 = **93.75%** | **95.12%** |

The global/runtime totals include all source modules in the named scopes, not just tests associated with this milestone. Compared with B03, the implementation is substantially larger; a lower percentage does not itself establish a regression.

Uncovered B04 paths were inspected rather than filled with arbitrary malformed-state cases:

- `core_machine.py`: 45 missing lines, primarily wrong-control/configuration/type/index checks, duplicate/unreserved binding guards, continuation-without-WHNF assertions, unsupported heap/continuation cases, defensive primitive fallback and hypothetical unsupported predefined arities. Examples: 147, 274, 506-537, 633-638, 819, 1144, 1212-1242, 1490-1500. The general unsupported-expression branch at 236 and force fallback at 788 also remain uncovered. These are real validation/unsupported-boundary coverage gaps, not proof those checks work for every input. Reviewed ordinary typed B04 paths reach neither the malformed-continuation guards nor future predefined arities.
- `result_consumer.py`: missing lines 39, 44, 60, 65, 77, 94, 146, 167, 239, 255, 260, 276, 287 concern configuration/machine mismatch, wrong phase/control, already-populated canonical state, inconsistent prior selection and wrong policy. Some are legitimate public misuse boundaries; others require a manually inconsistent state. They limit defensive API assurance, not the observed compiled-program result paths.
- `session_runner.py`: line 38, invalid `max_steps`, and line 96, an unsupported resolved mode; the latter requires bypassing the now-validated selector under trusted construction.
- `runtime/closures.py`: wrong-type input guards at 92, 95, 98, 140. `runtime/observation.py`: wrong heap/reference types and future unsupported heap values at 60, 69, 91. `runtime/heap.py:20` is the abstract base size accessor. Other runtime modules have all measured lines/branches covered, which is not a proof of complete state-space correctness.
- Static-pipeline gaps remain chiefly malformed-node/backstop paths in desugaring, name resolution, Core validation and parser fallback. Free-variable analysis misses its unknown internal action and unsupported-node/alternative guards. They do not constitute an uncovered implemented constructor evaluator.

### Supplementary deterministic probes

The two-batch matrix used CBV, evaluator limit 2,000 and node limit 1, with WHNF_ONLY/MATERIALIZE_COMPLETE_VALUE and every TraceMode. Programs were a literal; a three-global alias chain ending at `40 + 2`; a curried returned closure adding 20 and 22; a local recursive countdown to 42; local aliases and caller shadowing; `seq` storing/returning closures; a selected `if` whose other branch applies `1` as a function; and `seq (\x -> x) (seq 0)` returning an opaque partial function. For each of 48 configurations it checked all cuts `1 .. terminal_transition_index - 1`; their combined count was 2,334. These temporary probes were not used as additional coverage data or collected tests.

Other small source probes exercised global even/odd recursion, a returned recursive local closure, a forward global function alias under caller shadowing, leading-variable equation aliases and seq returning a function/partial function. Expected values/categories were observed. Two strict premature-initialization examples raised the documented error. They support the code review without replacing the retained reproducible regressions.

## 9. Known Limitations and Deferred Work

These are explicit scope boundaries or inherited accepted risks, not new B04 failures:

- No CBN/CBNeed execution, thunks, memoizing updates, sharing or blackhole rules. Current global reevaluation must not be described as shared evaluation.
- No executable constructors, lists, `CoreCase` or recursive constructor materialization; non-list matching/default behavior must be settled before B06 implements it.
- No GC, comparable experimental metrics, source-work attribution, full trace history/replay, STG execution, visualizer or RunRecord serialization.
- Internal dataclasses trust correctly typed immutable children. An external session/state import boundary must validate its own data. Mutation of arbitrary custom heap/frame subclasses is outside the accepted snapshot contract.
- Future thunk payloads cannot be mutated in place while shallow snapshots share them. Immutable successor payloads installed with `Heap.replace()` preserve the existing model; otherwise snapshot design must be deliberately revised. This is a concrete B05 implementation obligation, not an architecture blocker already reproduced in B04.
- Deep operational traversal passes, but generic deep Core dataclass equality/repr/hash can recurse. Consumers, diagnostics and future serialization should continue using iterative traversal or stable identities.
- Every successful evaluator transition copies heap and stack containers, including METRICS_ONLY execution. These host costs can grow with storage/stack size; this audit did not benchmark them. They must not be mistaken for abstract language-operation costs in later experiments.
- Errors currently propagate as explicit Python exceptions, and evaluator-budget stopping returns a reason with an inspectable running state; all enumerated failure/limit statuses are not automatically synthesized by this API. Terminal inputs themselves do not resume. Future controller/status normalization must preserve the documented evaluator-only and consumer boundaries.

## 10. Final Acceptance Decision

**ACCEPTED WITH LIMITATIONS.** The implemented B04 subset supplies the operational evaluator and canonical observation interface required for the B05 handoff. No Critical, High or Medium finding, no valid-program wrong result, and no demonstrated architecture blocker remains from this audit. Final ordinary and coverage suite runs both passed 1,623 tests. Added evidence specifically exercises recursive lexical identity, errors after partial initialization, and deep continuation resumption.

Unconditional documentary closure is limited by the open Low finding F01. Defensive API coverage is incomplete, and accepted typed-construction assumptions remain part of the boundary. These limits are explicit and do not require a CBV redesign before beginning B05. The proposed documentation correction was not performed because this first pass is an audit, not an automatic correction session.

Static validation, supported CBV operational correctness and experimental validity are distinct claims. This report strengthens the second within the reviewed subset and records evidence for the first; it does not certify the third or prove all executions correct.

## 11. Recommendations for B05

1. Repair F01's current status/navigation text in a separate small documentation change, preserving dated historical audits and accepted decisions. Estimate: **1-2 hours**; no mandatory production correction was identified.
2. Define immutable thunk lifecycle and update/blackhole continuations before adding mutable-looking states. Add snapshot and failed-transition tests around each state change; retain original anchors and references.
3. Specify CBNeed global activation/update identity separately from B04 `PendingGlobal` reevaluation. Test repeated demand through aliases, recursion, forwarding and parameter/default aliases before claiming at-most-once evaluation.
4. Preserve the shared Core representation and existing lexical captures. Replace CBV-only argument/local initialization paths with strategy-specific scheduling, rather than introducing name-based special cases or forcing captured fields accidentally.
5. Give non-strict `seq` its own operational demand rule. B04's first-argument-already-WHNF assertion is valid only because CBV partial application forces that argument; carrying it unchanged into deferred partial application would be incorrect.
6. Retain evaluator/consumer step separation, exact-boundary precedence and resumed-batch equivalence. Extend critical-property tests to thunk creation, update return, interrupted force and blackhole detection; keep errors, budget stops and true terminal states distinct.
7. Improve defensive boundary tests when those boundaries are introduced or changed. Do not replace a deliberate external validation contract with blanket validation/deep copying throughout internal transitions merely to increase coverage.
8. Keep raw transition/allocation counters separate from source-level reductions and generated binding costs until B07 defines attribution. Full tracing/GC/metrics experiments require their own evidence.

Only this report and the three new audit test files belong to the audit patch. No production module, existing test, specification, ADR, planning workbook or historical audit was changed; no commit was created.
