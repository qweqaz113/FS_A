import json

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from experiments.co2full_v4_baseline.run import (
    build_messages,
    load_baseline_pseudocode,
    parse_response,
    select_row_indices,
)


def test_parse_response_yes() -> None:
    parsed = parse_response(
        "<same_source>yes</same_source>\n<explanation>Equivalent logic.</explanation>"
    )
    assert parsed == {
        "same_function": True,
        "summary": "Equivalent logic.",
        "parse_status": "ok",
    }


def test_parse_response_no_case_insensitive() -> None:
    parsed = parse_response("<same_source> NO </same_source>")
    assert parsed["same_function"] is False
    assert parsed["parse_status"] == "ok_missing_explanation"


def test_parse_response_invalid() -> None:
    parsed = parse_response("I cannot determine the result.")
    assert parsed["same_function"] is None
    assert parsed["parse_status"] == "invalid_missing_same_source"


def test_build_messages_matches_original_few_shot_order() -> None:
    examples = [{"content": "example input", "reply": "example output"}]
    messages = build_messages(code_a="code A", code_b="code B", examples=examples)
    assert [type(message) for message in messages] == [
        SystemMessage,
        HumanMessage,
        AIMessage,
        HumanMessage,
    ]
    assert "Code A: code A" in str(messages[-1].content)
    assert "Code B: code B" in str(messages[-1].content)


def test_select_row_indices_without_label_limits_uses_row_limit(tmp_path) -> None:
    csv_path = tmp_path / "pairs.csv"
    csv_path.write_text("label\n1\n0\n0\n", encoding="utf-8")
    selected = select_row_indices(
        csv_path=csv_path,
        row_start=0,
        row_limit=2,
        label_1_limit=None,
        label_0_limit=None,
    )
    assert selected == [0, 1]


def test_empty_pseudocode_is_rejected_like_study_loader(tmp_path) -> None:
    code_dir = tmp_path / "Binkit-1.0-normal-strip-top_k_code" / "demo"
    code_dir.mkdir(parents=True)
    code_path = code_dir / "demo-1.0_binary.json"
    code_path.write_text(json.dumps({"0x1": {"pseudo_code": ""}}), encoding="utf-8")
    with pytest.raises(ValueError, match="Pseudocode is empty"):
        load_baseline_pseudocode(tmp_path, "demo-1.0_binary", "0x1")
