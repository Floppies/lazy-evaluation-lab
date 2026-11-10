# Lazy Evaluation Lab — Implementation Milestones (B01–B19)

This document provides a short reference for the implementation milestones used throughout the Lazy Evaluation Lab's specifications, architectural decisions, audits, and development documentation.

The descriptions follow the **Gantt B** plan and its milestone acceptance criteria. They summarize scope rather than implementation status; completion and deviations are tracked separately.

| ID | Milestone | Description |
|---|---|---|
| **B01** | Shared Technical Design | Define the common architecture and contracts for Core, STG-like IR, `lowerToStg`, canonical observation, execution states, snapshots, and metrics. |
| **B02** | Language Frontend and Core IR | Implement the source-to-Core pipeline: lexer, parser, Surface AST, validation, name resolution, desugaring, and Core representation. |
| **B03** | Runtime Infrastructure | Build runtime references, heap, stack, lexical environments, closures, `ExecutionState`, basic tracing, and a limited step-based execution interface. |
| **B04** | First Core Evaluator (CBV) | Implement the initial Core evaluation rules and the canonical observation interface, including explicit demand modes and result handling. |
| **B05** | Call by Need and Sharing | Introduce delayed computations, thunks, updates, sharing, blackhole handling, and the explicit stack behavior needed for Call by Need. |
| **B06** | Lists, Pattern Matching, and Recursion | Extend evaluation to constructors, `case`, mutually recursive bindings, list-processing programs (`map`, `take`, folds), and infinite lists. |
| **B07** | Instrumentation and Metrics | Define comparable evaluation and memory metrics, support data export, and distinguish semantic reductions from machine transitions. |
| **B08** | Interactive Visualizer | Provide stepping and replay with coordinated views of source code, current expressions, stack, heap graph, and metrics. |
| **B09** | Core-to-STG Lowering | Define the supported STG-like representation and implement `lowerToStg` for closures, bindings, applications, constructors, and case expressions. |
| **B10** | STG-like Machine | Execute the supported STG-like subset, apply canonical observation, compare observable results with Core, and explain operational differences. |
| **B11** | Call by Name | Implement delayed evaluation **without shared updates**, enabling experiments that expose the cost of repeated evaluation. |
| **B12** | Reachability and Garbage Collection | Implement correct GC roots, reachability traversal, mark-and-sweep collection, triggers, and GC events, with GC ON/OFF comparisons. |
| **B13** | Object Lifetime and Memory Visualization | Track object creation, first use, last use, unreachability, and collection; visualize lifetime timelines and live versus allocated heap memory. |
| **B14** | Preliminary Experiments | Validate experimental protocols, workloads, input sizes, smoke tests, and GC behavior before the final measurement campaign. |
| **B15** | Recursion: C and Haskell Comparison | Run reproducible experiments comparing linear recursion, accumulator-based recursion, lists, and reuse in C and Haskell, documenting compiler flags, RTS options, and evaluation demand. |
| **B16** | Final Experimental Campaign | Produce the final dataset across CBV, CBN, and CBNeed, applicable GC settings, and the common Core/STG-like subset. |
| **B17** | Continuous Testing and Integration | Maintain semantic, lowering, GC-root, replay, and regression tests throughout development, including cross-module integration. |
| **B18** | Incremental Report and Analysis | Develop the thesis report and methodology alongside implementation, then analyze the final experimental dataset and consolidate conclusions. |
| **B19** | Documentation, Demo, and Delivery | Package the software, dataset, scripts, README, user guide, report, appendices, and final demonstration. |

## Implementation Work Breakdown

| ID | Work package | Status |
|---|---|---|
| B02 | Language Frontend and Core IR | Completed |
| B02.1 | Repository Setup and Structure | Completed |
| B02.2 | Language Syntax Definition | Completed |
| B02.3 | Surface AST Design | Completed |
| B02.4 | Lexer | Completed |
| B02.5 | Parser | Completed |
| B02.6 | Frontend Tests | Completed |
| B02.7 | Core IR | Completed |
| B02.8 | Surface-to-Core Desugaring | Completed |
| B02.9 | Name Resolution | Completed |
| B02.10 | Semantic Validation | Completed |
| B02.11 | Integrated Compilation Pipeline | Completed |
| B02.12 | Documentation and Examples | Completed |
| B02.E | First-Class seq Extension | Completed |
| B02.E.1 | Predefined seq and Lexical Contract | Completed |
| B02.E.2 | Structural and Shadowing Tests | Completed |
| B02.E.3 | Specifications and Verification | Completed |
| B03 | Runtime Infrastructure | Completed |
| B03.1 | Lexical Environments | Completed |
| B03.2 | Heap and Basic Objects | Completed |
| B03.3 | Closures and Continuation Stack | Completed |
| B03.4 | ExecutionState and Snapshots | Completed |
| B03.5 | Basic Transitions, Batches and Tracing | Completed |
| B03.6 | Integration, Regression Tests and Audit | Completed |
| B04 | First Core Evaluator (CBV) | Completed |
| B04.1 | Evaluation Semantics and Contract | Completed |
| B04.2 | Core Program Initialization | Completed |
| B04.3 | Free Variables and Closure Capture | Completed |
| B04.4 | Core Function Evaluation (CBV) | Completed |
| B04.5 | Primitive Operations and Conditionals | Completed |
| B04.6 | CBV Recursive Local Bindings | Completed |
| B04.7 | First-Class seq Evaluation | Completed |
| B04.8 | Canonical Result Observation | Completed |
| B05 | Call by Need and Sharing | Completed |
| B05.1 | CBNeed Operational Contract | Completed |
| B05.2 | Thunk Representation and Allocation | Completed |
| B05.3 | Lazy Function Application | Completed |
| B05.4 | Forcing and Update Continuations | Completed |
| B05.5 | Memoization and Sharing | Completed |
| B05.6 | Global and Recursive Bindings | Completed |
| B05.7 | Blackhole Detection | Completed |
| B05.8 | Non-Strict seq Evaluation | Completed |
| B05.9 | Observation, Batching and Tracing | Completed |
| B05.10 | Integration and Regression Tests | Completed |
| B05.11 | Final Audit | Completed |
| B06 | Lists, Pattern Matching, and Recursion | In Progress |
| B06.1 | Constructor and Pattern-Matching Contract | Completed |
| B06.2 | Runtime Constructor Representation | Completed |
| B06.3 | CBNeed Constructor Evaluation | Completed |
| B06.4 | CBV Constructor Evaluation | Completed |
| B06.5 | CoreCase Evaluation and Matching | Completed |
| B06.6 | Pattern-Matching Errors and Edge Cases | Completed |
| B06.7 | Constructor WHNF Observation | Completed |
| B06.8 | Complete List Materialization | Completed |
| B06.9 | Recursive List Operations | Completed |
| B06.10 | Folds and Strictness | Completed |
| B06.11 | Infinite Lists and Bounded Evaluation | In Progress |
| B06.12 | Integration, Regressions and Audit | Pending |

### Important notes

The work packages listed above are internal subdivisions of
the canonical B01–B19 milestones. They do not introduce
additional Gantt milestones or change the approved scope.

Work packages document implementation sequencing and progress.
Operational semantics and permanent invariants are defined in
the corresponding technical contracts.

Audit reports preserve historical verification evidence,
acceptance decisions, limitations, and milestone-specific
implementation findings.

Future milestones will receive detailed work packages when
their implementation plans are established.

## Scope and naming notes

- **B02.E — First-Class `seq` Extension** is an additional, post-baseline task associated with B02. It introduces `seq` into the language specification, predefined scope, compiler pipeline, and frontend tests. Its operational demand behavior belongs to the evaluator milestones; B02.E alone does not execute `seq`.
- **B04, B05, and B11 are distinct evaluator milestones:** the initial Core evaluator begins with CBV in B04; B05 adds Call by Need and sharing; B11 adds nonmemoizing Call by Name. The shared interfaces and demand contracts may be designed earlier than their complete operational implementations.
- **B09 and B10 are separate:** B09 constructs STG-like IR; B10 executes it and compares canonical observable results with Core. Equivalent observable results do not imply identical operational traces or costs.
- **B17 and B18 are ongoing workstreams**, not stages performed only after B16.
- The Gantt also includes a separate **contingency allocation (B20)** for corrections and unforeseen work; it is not one of the B01–B19 implementation milestones listed above.

For detailed requirements, consult the technical specification, the current language specification, the accepted ADRs, and the canonical Gantt. Where the schedule and subsequently accepted decisions differ, record the revision explicitly rather than silently changing historical milestone scope.
