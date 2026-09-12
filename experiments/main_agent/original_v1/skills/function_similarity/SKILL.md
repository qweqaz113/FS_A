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

## References

- For confidence scoring, read `references/confidence_rubric.md`.
- For common IDA/Ghidra noise patterns, read `references/decompiler_noise.md`.
