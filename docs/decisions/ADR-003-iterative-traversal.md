# ADR-003: Use Iterative Traversals for Potentially Deep ASTs

- **Status:** Accepted for B02.8 traversal and validation paths
- **Recorded:** 2026-10-19
- **Scope:** Surface validation, Surface-to-Core lowering, Core validation and future deep-tree tooling
- **Related:** [Language specification](../specifications/language-specification.md), [B02.8 audit](../audits/b02.8-audit.md)

## Context

The parser builds left-associated operator/application trees without consuming its recursive-grammar nesting budget for each additional term. A valid expression such as a chain of 2,000 additions can therefore produce a Surface AST deeper than Python's call stack comfortably supports.

The initial Surface validator used recursive descent over AST nodes and raised `RecursionError` on such expressions, even though the parser and iterative desugaring could handle them. This broke the otherwise supported parse → validate → lower → Core-validate path.

The parser separately enforces its documented **64-context limit for recursively nested grammar constructs**. That parser limit is not intended to reject long flat chains, large list literals, or deep ASTs supplied programmatically to validation.

## Decision

Use explicit stacks or equivalent iterative traversals for operations that may process arbitrarily deep Surface/Core AST structures.

The current B02.8 implementation follows these rules:

1. **Surface validation:** Iterate through nodes without recursive descent; preserve validation rules, diagnostic visit order and nearest-located-ancestor span fallback.
2. **Surface-to-Core expression lowering:** Use an explicit postorder traversal, lowering children before constructing the parent Core node. Currying and list-spine construction use loops.
3. **Core validation:** Use an iterative traversal preserving structural checks and inherited source locations.
4. **Complexity:** Aim for O(n) work for ordinary finite AST trees and O(n) worst-case auxiliary storage, without repeatedly traversing entire subtrees.
5. **Parser:** Retain the separate, documented recursive-grammar nesting budget; do not bypass it or conflate it with AST traversal limits.

The accepted input contract for lowering is a **structurally validated, finite, acyclic Surface AST**. Lowering is not required to replace Surface validation or safely process cyclic/malformed manually assembled object graphs.

## Alternatives considered

1. **Increase `sys.setrecursionlimit`:** Rejected because it changes a process-global limit, does not remove structural fragility, and can cause stack exhaustion.
2. **Impose a smaller global AST-depth limit:** Rejected because it would unnecessarily reject legitimate long left-associative expressions already accepted by the parser.
3. **Keep recursive traversals and catch `RecursionError`:** Rejected because a preventable implementation limitation would still interrupt valid inputs.
4. **Switch the parser itself to fully iterative parsing immediately:** Not required for this issue; its recursive-grammar nesting rule is a separate documented language frontend contract.

## Consequences

### Benefits

- Deep valid ASTs can be validated and lowered without exhausting Python recursion.
- Large structures remain suitable for deterministic tests and future program analysis.
- Diagnostic locations can be retained with explicit traversal context.

### Obligations and limitations

- New analysis passes (including B02.9 name resolution, free-variable analysis, serialization and visualization traversals) should avoid unbounded recursive AST walking.
- Python dataclass-generated `__eq__`, `__hash__` and `__repr__` may still recurse deeply. **Do not assume** deep-tree equality, formatting or hashing is safe merely because validation/lowering is iterative; prefer iterative comparisons or serializers where needed (audit F06).
- Do not set a global recursion limit as a workaround.
- Tests should inspect deep tree shapes iteratively; using `==` on very deep separate trees can itself trigger `RecursionError`.
- Shared subtrees in programmatically constructed DAGs may be visited per occurrence; cycle handling and graph memoization are not part of this ADR.

## Verification and references

The [B02.8 audit](../audits/b02.8-audit.md) verifies the full 2,000-term addition pipeline; 2,000-deep manual valid/invalid ASTs; large lists, applications, lambdas, programs and equation groups; and Core validation. The audit reports no remaining recursion failure on supported validation/lowering inputs. Deep dataclass equality remains a documented tooling limitation (F06).

## Revisit when

Revisit this ADR if parser nesting policy changes, ASTs become graph-shaped or cyclic, or new traversals need different memory/performance tradeoffs. Do not silently remove long-input support.
