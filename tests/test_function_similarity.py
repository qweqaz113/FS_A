from enterprise_agent.agents.tools.function_similarity import (
    normalize_pseudocode,
    score_function_similarity,
)
from enterprise_agent.domain.function_similarity import parse_function_compare_input


def test_parse_function_pair() -> None:
    parsed = parse_function_compare_input("codea:\nreturn 1;\n\ncodeb:\nreturn 1;")

    assert parsed.code_a == "return 1;"
    assert parsed.code_b == "return 1;"


def test_normalization_removes_unstable_identifiers() -> None:
    normalized = normalize_pseudocode("int sub_401000(int a1) { return v2 + a1; }")

    assert "sub_401000" not in normalized
    assert "a1" not in normalized
    assert "v2" not in normalized


def test_identical_functions_receive_full_deterministic_score() -> None:
    code = 'int f(int a1) { puts("ok"); return a1 + 1; }'

    result = score_function_similarity(code, code)

    assert result["similarity"]["score"] == 1.0
