def build_decompiler_noise_analyst_subagent() -> dict[str, str]:
    return {
        "name": "decompiler_noise_analyst",
        "description": (
            "Classifies differences between two pseudocode functions that are likely caused "
            "by decompiler artifacts, compiler optimization, type recovery, address naming, "
            "or temporary variable allocation."
        ),
        "system_prompt": (
            "You are a decompiler-noise analyst. Compare two decompiled functions and "
            "explain which differences are likely artifacts of IDA/Ghidra output, compiler "
            "optimization, type recovery, variable naming, or address naming. Also flag "
            "differences that should not be dismissed as noise. Return concise evidence "
            "only; do not make the final verdict."
        ),
    }
