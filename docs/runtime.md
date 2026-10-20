@TODO: Make a clenear version

## Lexical Environments

Runtime environments associate variable names with RuntimeRef values.

Each environment contains local bindings and an optional parent
environment. Lookup searches from the innermost scope outward and
returns the stored reference without forcing or dereferencing it.

Extending an environment creates a new scope without modifying
existing scopes.

Recursive groups are constructed after their heap addresses have
been reserved. The environment does not allocate or initialize
heap objects.

Closure capture is handled separately and retains only the
required free local references.

Environment lookup is shared by CBV, CBN, and CBNeed. Strategy-
specific forcing and initialization belong to the evaluator.
