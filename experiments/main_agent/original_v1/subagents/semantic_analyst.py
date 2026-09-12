def build_semantic_analyst_subagent() -> dict[str, str]:
    return {
        "name": "semantic_analyst",
        "description": (
            "Finds evidence that two decompiled pseudocode functions implement the same "
            "behavior. Focuses on semantic intent, data flow, calls, strings, control flow, "
            "error paths, and return behavior."
        ),
        "system_prompt": (
            "You are a reverse-engineering semantic analyst. Compare two decompiled "
            "functions and identify evidence that they are likely the same original "
            "function. Prioritize stable behavior over names, addresses, stack offsets, "
            "and temporary variables. Return concise evidence only; do not make the final "
            "verdict."
        ),
    }
