# Confidence Rubric

Use these bands for final confidence.

## 0.90-1.00

Use only when the functions share nearly all stable evidence:
same core strings, same library/helper calls, same control-flow skeleton, same
important constants, same error paths, and same return behavior. Differences are
minor decompiler artifacts.

## 0.75-0.89

Use when the functions are very likely the same but one evidence family is
weaker or missing, such as renamed helpers, reordered temporary assignments, or
small formatting differences.

## 0.55-0.74

Use when there is meaningful overlap but also unresolved differences. This is
the normal range for "probably same" or "probably not same" when code is noisy,
partial, or optimized differently.

## 0.35-0.54

Use when evidence is mixed and neither side clearly wins. State the decisive
unknowns instead of pretending certainty.

## 0.10-0.34

Use when stable semantic evidence mostly differs: different strings, different
side effects, different control flow, different validation conditions, or
different return behavior.

## 0.00-0.09

Use when the functions are clearly unrelated or one input is not valid
pseudocode.

## Calibration Notes

- High confidence requires multiple independent evidence types.
- Identical helper addresses are useful only within the same binary/context.
- Identical signatures alone should not push confidence above 0.55.
- Identical error strings plus identical validation flow can be very strong.
- Missing strings in one function are not decisive if the decompiler omitted or
  folded string references.
- **Helper factoring across compilation targets reduces confidence in a
  "different" verdict.** If one function inlines phases that another factors
  into a helper, the call-set mismatch should be discounted. Model whether the
  helper absorbs the missing calls before treating the structural difference as
  semantic divergence. This keeps confidence in the 0.55-0.74 band (not lower)
  when the overall control-flow skeleton and downstream behavior match.
- **Cross-compiler/cross-optimization parameter type disagreements are weak
  evidence for a "different" verdict.** When one function's first parameter
  appears as a pointer and the other as a scalar, especially when the outer
  function passes the parameter to a helper without dereferencing it, this is
  likely a decompiler recovery artifact, not a semantic incompatibility. Do not
  reduce confidence below 0.55 on this basis alone.
- **Decompiler callback-arity differences are weak evidence for a "different"
  verdict when helpers mediate data flow.** An apparent 2-arg vs 0-arg callback
  mismatch may be a recovery artifact when a helper performs allocation and
  filtering before the call site. Discount this as structural noise rather than
  semantic evidence.
- **Same-project provenance reduces confidence in a "same" verdict.** When both
  functions originate from the same project, shared strings, global variable
  patterns, and data-structure skeletons are necessary but not sufficient for a
  same-function identification. Discount confidence by approximately 0.10-0.15
  relative to what you would assign for cross-project comparisons with
  equivalent evidence.
- **Cumulative unexplained differences should scale confidence downward.**
  When a comparison surfaces 3+ distinct categories of differences (parameter
  ordering, parameter types, control-flow structure, variable representations,
  buffer sizes, dead-code patterns) and all are dismissed as artifacts, reduce
  confidence by approximately 0.10-0.15 per additional category, with a floor
  of approximately 0.55 if the core algorithmic behavior, strings, and call
  sets remain aligned. **This applies especially when both functions share
  project provenance**, where genuinely different functions can exhibit
  moderate structural overlap.
- **Compiler clone specialization suffixes reduce confidence in a "same"
  verdict.** A `.constprop`, `.clone`, `.part`, or `.isra` suffix indicates
  the function is a compiler-generated specialization, which increases the
  probability of different-source identity even when surface features match.
  Reduce confidence by at least one full confidence band relative to the
  evidence alone.
