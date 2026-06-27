import json
from dataclasses import dataclass, field
from typing import Any

from enterprise_agent.agents.tools.function_similarity import score_function_similarity
from enterprise_agent.domain.function_similarity import (
    FunctionCompareInput,
    FunctionCompareInputError,
    parse_function_compare_input,
)
from enterprise_agent.domain.output_schema import FunctionSimilarityVerdict
from enterprise_agent.infra.config import get_settings


FORMATTER_MAX_ATTEMPTS = 3


@dataclass
class AgentRuntime:
    use_deepagents: bool = False
    _agent: Any | None = field(default=None, init=False, repr=False)
    _verdict_formatter: Any | None = field(default=None, init=False, repr=False)

    def invoke(self, message: str) -> str:
        compare_input = _try_parse_compare_input(message)
        if compare_input is not None:
            return self.compare_pair(compare_input=compare_input)

        result = self._get_agent().invoke({"messages": [{"role": "user", "content": message}]})
        return _extract_final_text(result)

    def compare_pair(self, *, compare_input: FunctionCompareInput) -> str:
        return self.run_pair(compare_input=compare_input)["output"]

    def run_pair(self, *, compare_input: FunctionCompareInput) -> dict[str, Any]:
        if not self.use_deepagents:
            baseline = score_function_similarity(compare_input.code_a, compare_input.code_b)
            verdict = _baseline_verdict(baseline)
            return {
                "output": _format_json_response(verdict),
                "verdict": verdict,
                "agent_result": {"baseline": baseline},
            }

        result = self._get_agent().invoke(
            {"messages": [{"role": "user", "content": compare_input.raw_message}]}
        )
        final_text = _extract_final_text(result)
        parsed = self._format_verdict(compare_input=compare_input, final_text=final_text)

        return {
            "output": _format_json_response(parsed),
            "verdict": parsed,
            "agent_result": result,
        }

    def _get_agent(self) -> Any:
        if self._agent is None:
            from enterprise_agent.agents.factory import create_enterprise_agent

            self._agent = create_enterprise_agent()
        return self._agent

    def _format_verdict(
        self, *, compare_input: FunctionCompareInput, final_text: str
    ) -> dict[str, Any]:
        parsed = _parse_json_object(final_text)
        if parsed is not None:
            normalized = _normalize_verdict_payload(parsed, raw_output=final_text)
            if normalized is not None:
                normalized["parse_status"] = "direct_json"
                return normalized

        errors: list[str] = []
        for attempt in range(1, FORMATTER_MAX_ATTEMPTS + 1):
            try:
                verdict = self._get_verdict_formatter().invoke(
                    [
                        ("system", _formatter_system_prompt(errors=errors, attempt=attempt)),
                        (
                            "user",
                            "Original comparison input:\n"
                            f"{compare_input.raw_message}\n\n"
                            "Agent final answer:\n"
                            f"{final_text}",
                        ),
                    ]
                )
                payload = verdict.model_dump() if hasattr(verdict, "model_dump") else dict(verdict)
                normalized = _normalize_verdict_payload(payload, raw_output=final_text)
                if normalized is not None:
                    normalized["parse_status"] = f"formatter_attempt_{attempt}"
                    if errors:
                        normalized["formatter_retry_errors"] = errors
                    return normalized
                errors.append(
                    f"attempt {attempt}: formatter returned unusable payload: {payload!r}"
                )
            except Exception as exc:
                errors.append(f"attempt {attempt}: {exc}")

        repair = _text_fallback_verdict(final_text)
        if repair is not None:
            repair["parse_status"] = "text_fallback"
            repair["formatter_retry_errors"] = errors
            return repair

        fallback = _invalid_json_verdict(final_text)
        fallback["format_error"] = errors[-1] if errors else "Unknown formatter error."
        fallback["formatter_retry_errors"] = errors
        return fallback

    def _get_verdict_formatter(self) -> Any:
        if self._verdict_formatter is None:
            from langchain_deepseek import ChatDeepSeek

            settings = get_settings()
            model_name = settings.llm_model.removeprefix("deepseek:")
            llm = ChatDeepSeek(model=model_name)
            self._verdict_formatter = llm.with_structured_output(
                FunctionSimilarityVerdict,
                method="json_mode",
            )
        return self._verdict_formatter


def _formatter_system_prompt(*, errors: list[str], attempt: int) -> str:
    feedback = ""
    if errors:
        feedback = (
            "\nPrevious formatting attempt(s) failed:\n"
            + "\n".join(f"- {error}" for error in errors[-3:])
            + "\nFix only the JSON structure while preserving the verdict meaning."
        )
    return (
        "Convert the reverse-engineering agent's final answer into the required "
        "structured JSON verdict. Preserve the original judgment, confidence, and evidence. "
        "The confidence field is confidence in the final same_function verdict, not "
        "the probability that same_function is true. If the final verdict is different "
        "and the answer says there is only 0.10 confidence/probability they are the same, "
        "set same_function to false and confidence to 0.90. "
        "Return only valid JSON matching exactly these keys: same_function, confidence, "
        "summary, matching_evidence, difference_evidence, noise_assessment. "
        "If the source text has a single evidence/explanation field, put it in summary "
        "and also in matching_evidence or difference_evidence depending on the verdict. "
        f"This is formatting attempt {attempt} of {FORMATTER_MAX_ATTEMPTS}."
        f"{feedback}"
    )


def _normalize_verdict_payload(
    payload: dict[str, Any], *, raw_output: str
) -> dict[str, Any] | None:
    same_function = _coerce_same_function(payload)
    confidence = _coerce_confidence(payload.get("confidence", payload.get("score")))
    if same_function is None or confidence is None:
        return None

    evidence_text = _first_text(
        payload.get("summary"),
        payload.get("evidence"),
        payload.get("reason"),
        payload.get("explanation"),
        payload.get("rationale"),
        raw_output if not payload.get("summary") else None,
    )
    summary = evidence_text or "Function similarity verdict produced by the agent."
    matching_evidence = _coerce_string_list(payload.get("matching_evidence"))
    difference_evidence = _coerce_string_list(payload.get("difference_evidence"))
    noise_assessment = _coerce_string_list(payload.get("noise_assessment"))

    if not matching_evidence and not difference_evidence:
        if same_function:
            matching_evidence = [summary]
        else:
            difference_evidence = [summary]

    return {
        "same_function": same_function,
        "confidence": confidence,
        "summary": summary,
        "matching_evidence": matching_evidence,
        "difference_evidence": difference_evidence,
        "noise_assessment": noise_assessment,
    }


def _coerce_same_function(payload: dict[str, Any]) -> bool | None:
    for key in ("same_function", "same", "is_same", "equivalent"):
        if key in payload:
            value = _coerce_bool(payload[key])
            if value is not None:
                return value
    verdict = payload.get("verdict") or payload.get("label") or payload.get("decision")
    if verdict is None:
        return None
    text = str(verdict).strip().lower()
    if text in {"same", "same_function", "equivalent", "true", "yes", "match", "matching"}:
        return True
    if text in {"different", "not_same", "not same", "false", "no", "mismatch", "nonmatch"}:
        return False
    return None


def _coerce_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        if value == 1:
            return True
        if value == 0:
            return False
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"true", "yes", "same", "equivalent", "match", "matching"}:
            return True
        if text in {"false", "no", "different", "not same", "not_same", "mismatch"}:
            return False
    return None


def _coerce_confidence(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        confidence = float(value)
    elif isinstance(value, str):
        text = value.strip().lower()
        if text.endswith("%"):
            try:
                confidence = float(text[:-1].strip()) / 100.0
            except ValueError:
                return None
        elif text in {"high", "very high"}:
            confidence = 0.9
        elif text in {"medium", "moderate"}:
            confidence = 0.65
        elif text in {"low", "weak"}:
            confidence = 0.35
        else:
            try:
                confidence = float(text)
            except ValueError:
                return None
    else:
        return None
    if confidence > 1.0 and confidence <= 100.0:
        confidence = confidence / 100.0
    if 0.0 <= confidence <= 1.0:
        return round(confidence, 4)
    return None


def _coerce_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    return [text] if text else []


def _first_text(*values: Any) -> str:
    for value in values:
        if value is None:
            continue
        if isinstance(value, list):
            text = "; ".join(str(item).strip() for item in value if str(item).strip())
        else:
            text = str(value).strip()
        if text:
            return text
    return ""


def _text_fallback_verdict(text: str) -> dict[str, Any] | None:
    lowered = text.lower()
    same_markers = ("same function", "same original function", "equivalent", "identical")
    different_markers = ("different function", "not the same", "not same", "unrelated")
    same_hits = sum(marker in lowered for marker in same_markers)
    different_hits = sum(marker in lowered for marker in different_markers)
    if same_hits == different_hits:
        return None
    same_function = same_hits > different_hits
    confidence = _extract_confidence_from_text(text) or 0.55
    summary = text.strip()[:1200] or "Recovered verdict from raw text."
    return {
        "same_function": same_function,
        "confidence": confidence,
        "summary": summary,
        "matching_evidence": [summary] if same_function else [],
        "difference_evidence": [] if same_function else [summary],
        "noise_assessment": [],
    }


def _extract_confidence_from_text(text: str) -> float | None:
    import re

    patterns = [
        r"confidence\s*[:=]\s*(\d+(?:\.\d+)?)\s*%",
        r"confidence\s*[:=]\s*(0?\.\d+|1(?:\.0+)?)",
        r"(\d+(?:\.\d+)?)\s*%\s*confidence",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            suffix = "%" if "%" in match.group(0) else ""
            return _coerce_confidence(match.group(1) + suffix)
    return None


def run_demo(notes: str) -> str:
    return AgentRuntime(use_deepagents=False).invoke(notes)


def _try_parse_compare_input(message: str) -> FunctionCompareInput | None:
    try:
        return parse_function_compare_input(message)
    except FunctionCompareInputError:
        return None


def _baseline_verdict(baseline: dict[str, Any]) -> dict[str, Any]:
    score = float(baseline["similarity"]["score"])
    same_function = score >= 0.65
    confidence = score if same_function else 1.0 - score
    return {
        "same_function": same_function,
        "confidence": round(confidence, 4),
        "summary": "Deterministic baseline only; enable DeepAgents for multi-agent review.",
        "matching_evidence": baseline["similarity"]["explanation"],
        "difference_evidence": [],
        "noise_assessment": [
            "Function names, helper addresses, temporary variables, and stack offsets were normalized."
        ],
        "baseline_similarity": baseline["similarity"],
    }


def _extract_final_text(result: Any) -> str:
    if not isinstance(result, dict):
        return str(result)
    messages = result.get("messages", [])
    if not messages:
        return str(result)
    last_message = messages[-1]
    if isinstance(last_message, dict):
        content = last_message.get("content", last_message)
    else:
        content = getattr(last_message, "content", last_message)
    if isinstance(content, list):
        return "\n".join(str(item) for item in content)
    return str(content)


def _parse_json_object(text: str) -> dict[str, Any] | None:
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()

    try:
        value = json.loads(stripped)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def _invalid_json_verdict(raw_output: str) -> dict[str, Any]:
    return {
        "same_function": None,
        "confidence": None,
        "summary": "Agent output was not valid JSON and could not be converted to the schema.",
        "matching_evidence": [],
        "difference_evidence": [],
        "noise_assessment": [],
        "raw_output": raw_output,
    }


def _format_json_response(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)
