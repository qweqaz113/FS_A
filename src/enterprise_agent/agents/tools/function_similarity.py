from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import asdict, dataclass
from typing import Any


_COMMENT_RE = re.compile(r"//.*?$|/\*.*?\*/", re.DOTALL | re.MULTILINE)
_ADDRESS_RE = re.compile(r"\b(?:sub|loc|off|byte|word|dword|qword|unk)_[0-9A-Fa-f]+\b")
_STACK_COMMENT_RE = re.compile(r"\s*;\s*//.*$")
_STRING_RE = re.compile(r'"(?:\\.|[^"\\])*"')
_CALL_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(")
_CASE_RE = re.compile(r"\bcase\s+([^:]+)\s*:")
_VAR_RE = re.compile(r"\b(?:v\d+|a\d+|result)\b")

_KEYWORDS = {
    "if",
    "for",
    "while",
    "switch",
    "return",
    "sizeof",
    "case",
}


@dataclass(frozen=True)
class PseudocodeFeatures:
    line_count: int
    calls: list[str]
    strings: list[str]
    case_labels: list[str]
    control_keywords: dict[str, int]
    constants: list[str]
    error_markers: list[str]
    normalized: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SimilarityScore:
    score: float
    call_overlap: float
    string_overlap: float
    case_overlap: float
    control_overlap: float
    constant_overlap: float
    explanation: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def normalize_pseudocode(code: str) -> str:
    """Normalize IDA-like pseudocode while preserving semantic anchors."""
    code = _COMMENT_RE.sub("", code)
    lines: list[str] = []
    for raw_line in code.splitlines():
        line = _STACK_COMMENT_RE.sub("", raw_line).strip()
        if not line:
            continue
        line = _ADDRESS_RE.sub("ADDR", line)
        line = _VAR_RE.sub("VAR", line)
        line = re.sub(r"\s+", " ", line)
        lines.append(line)
    return "\n".join(lines)


def extract_pseudocode_features(code: str) -> dict[str, Any]:
    """Extract stable comparison features from IDA-like pseudocode."""
    normalized = normalize_pseudocode(code)
    body_for_calls = "\n".join(normalized.splitlines()[1:])
    calls = [
        _normalize_call_name(match.group(1))
        for match in _CALL_RE.finditer(body_for_calls)
        if match.group(1) not in _KEYWORDS
    ]
    strings = [_clean_string(value) for value in _STRING_RE.findall(normalized)]
    case_labels = [label.strip() for label in _CASE_RE.findall(normalized)]
    control_keywords = {
        keyword: len(re.findall(rf"\b{keyword}\b", normalized))
        for keyword in ("if", "else", "switch", "case", "for", "while", "return", "abort", "exit")
    }
    constants = sorted(set(re.findall(r"(?<![A-Za-z_])[-+]?\d+(?:\.\d+)?", normalized)))
    error_markers = [
        marker
        for marker in ("error", "fprintf", "stderr", "exit", "abort", "gettext")
        if re.search(rf"\b{marker}\b", normalized)
    ]
    features = PseudocodeFeatures(
        line_count=len(normalized.splitlines()),
        calls=sorted(set(calls)),
        strings=sorted(set(strings)),
        case_labels=sorted(set(case_labels)),
        control_keywords=control_keywords,
        constants=constants,
        error_markers=error_markers,
        normalized=normalized,
    )
    return features.to_dict()


def score_function_similarity(code_a: str, code_b: str) -> dict[str, Any]:
    """Compute a deterministic baseline similarity score for two pseudocode functions."""
    features_a = extract_pseudocode_features(code_a)
    features_b = extract_pseudocode_features(code_b)

    call_overlap = _jaccard(features_a["calls"], features_b["calls"])
    string_overlap = _jaccard(features_a["strings"], features_b["strings"])
    case_overlap = _jaccard(features_a["case_labels"], features_b["case_labels"])
    control_overlap = _counter_similarity(
        Counter(features_a["control_keywords"]),
        Counter(features_b["control_keywords"]),
    )
    constant_overlap = _jaccard(features_a["constants"], features_b["constants"])

    score = (
        0.30 * call_overlap
        + 0.30 * string_overlap
        + 0.15 * control_overlap
        + 0.15 * case_overlap
        + 0.10 * constant_overlap
    )
    similarity = SimilarityScore(
        score=round(score, 4),
        call_overlap=round(call_overlap, 4),
        string_overlap=round(string_overlap, 4),
        case_overlap=round(case_overlap, 4),
        control_overlap=round(control_overlap, 4),
        constant_overlap=round(constant_overlap, 4),
        explanation=_score_explanation(
            call_overlap=call_overlap,
            string_overlap=string_overlap,
            case_overlap=case_overlap,
            control_overlap=control_overlap,
            constant_overlap=constant_overlap,
        ),
    )
    return {
        "features_a": features_a,
        "features_b": features_b,
        "similarity": similarity.to_dict(),
    }


def format_similarity_result(result: dict[str, Any]) -> str:
    return json.dumps(result, ensure_ascii=False, indent=2)


def _normalize_call_name(name: str) -> str:
    return _ADDRESS_RE.sub("ADDR", name)


def _clean_string(value: str) -> str:
    return value.strip('"')


def _jaccard(left: list[str], right: list[str]) -> float:
    left_set = set(left)
    right_set = set(right)
    if not left_set and not right_set:
        return 1.0
    if not left_set or not right_set:
        return 0.0
    return len(left_set & right_set) / len(left_set | right_set)


def _counter_similarity(left: Counter, right: Counter) -> float:
    keys = set(left) | set(right)
    if not keys:
        return 1.0
    intersection = sum(min(left[key], right[key]) for key in keys)
    union = sum(max(left[key], right[key]) for key in keys)
    return intersection / union if union else 1.0


def _score_explanation(
    *,
    call_overlap: float,
    string_overlap: float,
    case_overlap: float,
    control_overlap: float,
    constant_overlap: float,
) -> list[str]:
    explanations: list[str] = []
    if string_overlap >= 0.8:
        explanations.append("String constants are highly similar.")
    elif string_overlap <= 0.2:
        explanations.append("String constants differ substantially.")

    if call_overlap >= 0.7:
        explanations.append("Function-call sets are strongly overlapping.")
    elif call_overlap <= 0.3:
        explanations.append("Function-call sets have weak overlap.")

    if case_overlap >= 0.8:
        explanations.append("Switch/case labels are highly similar.")
    elif case_overlap <= 0.2:
        explanations.append("Switch/case labels differ substantially.")

    if control_overlap >= 0.8:
        explanations.append("Control-flow keyword counts are similar.")
    if constant_overlap >= 0.7:
        explanations.append("Numeric constants overlap strongly.")

    return explanations
