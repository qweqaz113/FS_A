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
