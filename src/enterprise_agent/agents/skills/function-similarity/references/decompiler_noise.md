# Decompiler Noise Guide

These differences are usually weak evidence.

## Names And Addresses

- `v1`, `v2`, `a1`, `result`
- stack offsets such as `[sp+20h] [bp-1E0h]`
- register comments such as `// r0`
- IDA labels such as `loc_`, `off_`, `byte_`, `dword_`

## Type Recovery

Decompilers often disagree on:

- signedness
- `int` vs pointer-looking integer
- `char *` vs `const char *`
- integer width
- `float`/`double` coercion helpers
- structure field types

Treat type differences as important only when they change observable behavior.

## Control Flow Shape

Optimizers and decompilers may render equivalent logic differently:

- `if/else` vs early return
- `switch` vs chained `if`
- inverted conditions
- temporary boolean variables
- duplicated cleanup blocks

Look for the same predicates, side effects, and terminal actions rather than
surface syntax.

## Strong Evidence Despite Noise

These are usually stable:

- distinctive strings and format strings
- unusual constants
- ordered library calls
- parse/validate/convert pipelines
- error-reporting and exit behavior
- allocation/free ownership patterns
- file/network/crypto side effects

## Callback/Function-Pointer Arity

Decompiler-recovered callback argument counts are **unreliable** when a helper
function mediates data flow between allocation and the call site.

**Why:** Decompilers recover callback arguments by inspecting register stores
and stack pushes immediately before the call instruction. When a helper performs
allocation, filtering, sorting, or other processing, the register setup for the
callback argument may reside in a different basic block or register allocation
may alias, causing the decompiler to drop arguments entirely.

**How to handle:** Treat an apparent callback arity mismatch (e.g., 2 args in
one function vs 0 args in the other) as weak evidence when a helper mediates
the data flow. Check whether the surrounding allocation/call pattern suggests
the same logical callback contract. Decompilers do not reliably recover
function-pointer signatures across helper boundaries.

## Helper Factoring (Inlining vs Outlining)

When functions compiled from the same source are optimized differently, one may
inline phases (allocate, filter, sort, iterate) while the other factors the same
phases into a helper. This can produce dramatically different call signatures.

**How it manifests:**
- One function calls `malloc`, `qsort`, and the callback inline; the other
  delegates all three to a single `sub_XXXXXX`.
- Deterministic similarity tools report low call overlap (e.g., 75%) because
  calls are absorbed inside the helper.
- The apparent structural difference is cosmetic — the helper encapsulates the
  same logical phases that are inlined in the counterpart.

**How to handle:** Before listing missing calls or different helper structure as
difference evidence, model whether the helper could absorb the counterpart's
inlined phases. This is particularly important when the overall control-flow
skeleton (null-terminated traversal, iterate-and-callback pattern) matches.

## Cross-Compiler / Cross-Optimization Parameter Type Recovery

Parameter type recovery varies systematically across compilers, optimization
levels, and decompiler versions.

**Common recovery artifacts:**
- `unsigned __int64*` vs `int` for the same register argument
- `int` vs pointer-looking integer
- struct field access visible in one decompilation, opaque in another
- signedness disagreements

**Why:** Decompiler type recovery depends on how the calling convention and
register aliasing propagate type information. When a function is a thin wrapper
that forwards its first parameter to a helper without dereferencing it, the
outer function's recovered type depends on compiler-specific register coloring
and optimization passes. GCC and Clang at different optimization levels may
radically disagree.

**How to handle:** Evaluate parameter roles (what the parameter is used for
downstream) rather than relying on recovered type signatures. A parameter that
serves as a hash-table handle in both functions is equivalent even if one
decompiler shows a pointer and the other shows an integer. Parameter type
disagreements should reduce confidence only weakly, especially when downstream
usage (passing to a helper that produces consistent results) is compatible.

## What NOT to Dismiss as Noise

The decompiler-noise framing is valuable but can lead to over-dismissal of
genuine differences. The following features must **not** be treated as noise:

1. **Algorithmic strategy differences** — e.g., collision-resolution method
   (fixed-slot vs linear-probing vs chaining), sorting order, tree vs hash
   vs list. These are fundamental algorithmic divergences that no compiler
   or decompiler can introduce or remove.

2. **Side-effect contract differences** — whether a function checks for
   duplicates before inserting (idempotent) vs writing unconditionally
   (non-idempotent). These reflect different API contracts, not optimization
   artifacts.

3. **Guard-condition placement differences that change observable behavior**
   — a null-check on an input parameter at function entry vs a null-check on
   a derived pointer inside a conditional branch. These reflect different
   control-flow intent.

4. **Presence/absence of validation or return-code checking** — one function
   validates and returns an error code; the other assumes success. This is a
   genuine semantic contract difference.

5. **Cumulative pattern of multiple independently-plausible noise items.**
   While any single difference (e.g., variable renaming, temporary assignment
   reordering, type recovery variation) can be dismissed as noise in isolation,
   the presence of 3+ distinct categories of such differences should not be
   cumulatively dismissed. The total count of artifact-dependent explanations
   is itself a signal that the functions may genuinely differ at source level.
