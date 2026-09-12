def build_difference_analyst_subagent() -> dict[str, str]:
    return {
        "name": "difference_analyst",
        "description": (
            "Finds evidence that two decompiled pseudocode functions differ in observable "
            "behavior. Focuses on mismatched validation, side effects, calls, strings, "
            "branches, state changes, and return values."
        ),
        "system_prompt": (
            "You are a reverse-engineering differential analyst. Compare two decompiled "
            "functions and identify evidence that they may not be the same original "
            "function. Ignore weak differences such as temporary variable names or helper "
            "addresses unless they imply behavior changes. Return concise evidence only; "
            "do not make the final verdict."
        ),
    }
