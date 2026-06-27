from enterprise_agent.agents.tools.function_similarity import (
    extract_pseudocode_features,
    normalize_pseudocode,
    score_function_similarity,
)


def build_tools() -> list:
    return [
        normalize_pseudocode,
        extract_pseudocode_features,
        score_function_similarity,
    ]
