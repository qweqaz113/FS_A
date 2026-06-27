---
name: function-similarity
description: Use this skill when comparing two IDA/Ghidra/decompiler pseudocode functions to decide whether they are likely the same original function, including same/not-same verdicts with confidence scores and evidence.
license: MIT
metadata:
  version: "1.0"
---

# Function Similarity Skill

Use this workflow when the user provides two decompiled pseudocode blocks labeled
`codea:` and `codeb:` and asks whether they are the same function.

## Workflow

1. Parse the input as two blocks: `codea` and `codeb`.
2. Normalize both functions before reasoning about names or addresses.
3. Extract stable features:
   - string constants and format strings
   - external/library calls
   - helper-call sequence and repeated call patterns
   - control-flow shape, especially branches, loops, switch/case labels, and exits
   - error paths, logging, file I/O, allocation, parsing, and return behavior
   - parameter roles (what the parameter is used for, not its recovered type)
4. Ask specialist subagents for independent evidence:
   - semantic analyst: evidence that the functions match
   - difference analyst: behavior that may prove they differ
   - decompiler-noise analyst: differences likely caused by decompiler artifacts
5. Produce a final verdict in JSON-compatible form.

## Output Contract

Return exactly one final object with these fields:

```json
{
  "same_function": true,
  "confidence": 0.0,
  "summary": "",
  "matching_evidence": [],
  "difference_evidence": [],
  "noise_assessment": []
}
```

`confidence` must be between `0.0` and `1.0`.

## Decision Rules

- Treat function names, addresses, temporary variable names, stack offsets, and
  register names as weak evidence.
- Treat identical or near-identical strings, call sets, control-flow skeletons,
  switch cases, error paths, and return semantics as strong evidence.
- Do not mark functions as the same solely because both are short, both use
  common libc calls, or both have similar signatures.
- Prefer calibrated uncertainty over forced certainty.

## Same-Project Reasoning

When both functions originate from the same software project (as determined by
shared global data structures, identical project-specific strings, or matching
internal helper patterns), **same-project provenance reduces the weight of
certain evidence types**:

### String Identity Is Weaker Evidence Within the Same Project

Identical string constants in two functions from the same project do not imply
same-function identity — they can arise from shared templates, macros, inlined
helpers, or centralized error-reporting utilities. String identity across
same-project cross-architecture pairs is **necessary but not sufficient** for a
same-function verdict. When strings match but the algorithmic pattern is generic
(e.g., error reporting, configuration parsing, format conversion), treat this as
moderate evidence rather than strong.

### Global Variable Correspondence Is Weak Evidence Within the Same Project

Two functions from the same project that implement the same abstract data
structure (e.g., hash-map insertion) will naturally access analogous globals
(base pointer, capacity, index, chain head/tail, flag byte). The fact that
globals appear in a similar pattern simply confirms both functions operate on
the same data structure type — it does not prove they originate from the same
source-level function. **Global variable correspondence across two functions in
the same binary is weak evidence of function equivalence.**

### Shared Data-Structure Skeleton Is Not Shared Identity

When both candidates implement the same abstract data structure (e.g., a hash
map insertion, a linked-list traversal, a lazy-init + realloc pattern), the
presence of matching structural phases is expected even for different functions.
The shared skeleton is a necessary but not sufficient condition. The
distinguishing evidence lies in the details: how collisions are resolved,
whether duplicates are checked, where guard conditions are placed, and what
API-level contract (idempotent vs non-idempotent) each function enforces.
Always require these fine-grained semantic details to converge before ruling
functions as same-source.

### Hard Diagnostic Features (Treat as Strong Counter-Evidence)

When the following features differ between two functions, they are **hard
diagnostic evidence of different-source identity** — do not dismiss them as
decompiler artifacts:

1. **Collision-resolution strategy**: Fixed-slot vs advancing/linear-probing vs
   chaining strategy differences are fundamental algorithmic divergences no
   compiler can introduce or remove.
2. **Idempotent vs non-idempotent side-effect contracts**: One function checks
   for duplicates before writing; the other unconditionally overwrites. These
   constitute different API contracts and cannot be explained by optimization.
3. **Explicit guard-condition placement**: A null-guard on an input parameter
   (outermost, unconditional) vs a guard on a derived pointer (at a specific
   label) reflects different control-flow intent, not a commutative compiler
   transform.
4. **Presence or absence of validation logic**: One function validates input
   ranges or return codes; the other does not. This is a genuine semantic
   difference in the function's interface contract.

These features should be weighted heavily in the final verdict, often decisive.

## Compiler Clone / Specialization Awareness

Compiler-generated function clones (indicated by `.constprop`, `.clone`,
`.part`, `.isra`, `.constprop.0`, or similar optimization suffixes in function
names or symbol metadata) signal that the function is a specialized variant.
When one function has such a suffix and the other does not:

- The probability that they are different-source functions **increases** even
  when surface features match.
- The function with the clone suffix may be a constant-folded, partial-inlined,
  or argument-specialized variant of a different source-level function.
- Treat matching evidence as weaker than usual when a clone suffix is present.
- Differences that would be weak noise in a normal comparison should receive
  more weight and more scrutiny.

**Rule of thumb**: When one candidate carries a compiler-clone suffix, reduce
confidence in a same-function verdict by at least one confidence band compared
to the similarity of the evidence alone.

## Cumulative-Difference Confidence Calibration

Each individual decompiler or compiler artifact may be noise-plausible in
isolation, but the **total count and diversity** of differences must inform
confidence calibration:

- When a comparison surfaces 3+ distinct categories of differences (parameter
  ordering, parameter types, control-flow structure, variable representations,
  buffer sizes, dead-code patterns) and all are dismissed as artifacts, the
  cumulative uncertainty must lower confidence.
- **Especially when both functions share project provenance**: the same project
  can contain genuinely different functions that share moderate structural
  overlap. Multiple artifact-dependent explanations should reduce confidence
  from near-certain to moderate.
- A rule of thumb: each additional independent category of dismissed difference
  should reduce confidence by approximately 0.10-0.15, with a floor of ~0.55
  if the core algorithmic behavior, strings, and call sets remain aligned.

## Decompiler Artifact Awareness

### Callback/Function-Pointer Arity

Decompiler-recovered callback argument counts are **weak evidence** when a
helper function mediates the data flow between allocation and the call site.
Decompilers recover callback arguments by inspecting setup instructions
immediately before the call. When a helper performs allocation, filtering, or
sorting, the register setup for the callback argument may be in a different
basic block, causing the decompiler to drop arguments. If the apparent arity
mismatch could be explained by helper-mediated data flow, do not treat it as
definitive evidence of semantic incompatibility.

### Helper Factoring / Inlining-Outlining

When one function inlines multiple phases (allocate, filter, sort, iterate) and
the other delegates the same phases to a helper, the difference in helper-call
structure is **weak evidence** of behavioral difference. Before listing missing
calls or changed helper structure as difference evidence, model whether the
helper could absorb the counterpart function's inlined phases. A mismatched
helper-call pattern across compilation targets is often a cosmetic boundary
artifact, not a semantic divergence.

### Cross-Compiler / Cross-Optimization Parameter Type Recovery

First-parameter type differences (especially pointer-to-scalar disagreements)
are **weak evidence** across different compilers and optimization levels,
particularly when one function is a thin wrapper that passes the parameter to a
helper without dereferencing it. Decompiler type recovery depends on how the
calling convention and register aliasing propagate type information; GCC and
Clang at different optimization levels may recover radically different types
for the same register. Evaluate parameter roles (how the parameter is used
downstream) rather than relying on recovered type signatures.

## Evidence Weighting Guidance

| Evidence Type | Weight | Notes |
|---|---|---|
| Identical distinctive strings | Strong (moderate if same-project) | Survives optimization; weaker when same project due to template/macro reuse |
| Same-project string identity | Moderate | Necessary but not sufficient for same-function verdict |
| Identical library call sequence | Strong | Within same binary context |
| Identical control-flow skeleton | Strong | Same branches, loops, switch labels |
| Identical error/return behavior | Strong | Error paths survive inlining differently but preserve predicates |
| Collision-resolution / algorithmic strategy difference | Decisive (strong counter-evidence) | Fundamental algorithmic divergence no compiler can introduce |
| Idempotency / API contract difference | Decisive (strong counter-evidence) | Different side-effect contracts are genuine |
| Global variable correspondence (same-project) | Weak | Confirms same data structure type, not same function |
| Mismatched helper-call structure | Weak | Likely inlining/outlining artifact |
| Compiler clone suffix present | Reduces weight of all matching evidence | Specialization increases probability of different-source identity |
| Decompiler callback arity difference | Weak | When helper mediates data flow to callback |
| First-param type (pointer vs scalar) | Weak | Especially across different compiler/opt levels |
| Function/helper names or addresses | Weak | Renamed across compilations |
| Temporary variable names, stack offsets | Weak | Decompiler-generated |
| Call set overlap < 0.5 with helper factoring | Medium | Must check whether helper absorbs missing calls first

## References

- For confidence scoring, read `references/confidence_rubric.md`.
- For common IDA/Ghidra noise patterns, read `references/decompiler_noise.md`.
