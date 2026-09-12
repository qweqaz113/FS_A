from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from enterprise_agent.agents.runtime import AgentRuntime
from enterprise_agent.domain.function_similarity import FunctionCompareInput
from enterprise_agent.benchmarks.co2full.dataset import load_co2full_pair_by_row
from enterprise_agent.benchmarks.co2full.recorder import ExperimentRecorder


def compare_loaded_pair(
    *,
    compare_input: FunctionCompareInput,
    source_metadata: dict[str, Any] | None = None,
    runtime: AgentRuntime | None = None,
    trace_dir: str | Path,
    report_dir: str | Path,
) -> dict[str, Any]:
    runtime = runtime or AgentRuntime(use_deepagents=False)
    recorder = ExperimentRecorder.start(
        compare_input=compare_input,
        source_metadata=source_metadata,
        trace_dir=trace_dir,
        report_dir=report_dir,
    )

    try:
        if hasattr(runtime, "run_pair"):
            run_result = runtime.run_pair(compare_input=compare_input)
            verdict = _coerce_verdict(run_result.get("verdict"))
            recorder.record_agent_result(run_result.get("agent_result"))
        else:
            raw_output = runtime.compare_pair(compare_input=compare_input)
            verdict = _parse_json_object(raw_output) or _invalid_json_verdict(raw_output)
            recorder.record_agent_result({"raw_output": raw_output})

        recorder.record_verdict(verdict)
        trace_path, report_path = recorder.save_all()
        return {
            "trace_id": recorder.trace_id,
            "pair_key": recorder.pair_key,
            "trace_path": trace_path.as_posix(),
            "report_path": report_path.as_posix(),
            "verdict": verdict,
        }
    except Exception as exc:
        recorder.record_error(exc)
        recorder.save_trace()
        raise


def compare_co2full_row(
    *,
    row_index: int,
    csv_path: str | Path | None = None,
    db_root: str | Path | None = None,
    runtime: AgentRuntime | None = None,
    trace_dir: str | Path,
    report_dir: str | Path,
) -> dict[str, Any]:
    loaded = load_co2full_pair_by_row(
        row_index=row_index,
        csv_path=csv_path,
        db_root=db_root,
    )
    return compare_loaded_pair(
        compare_input=loaded["compare_input"],
        source_metadata=loaded["source_metadata"],
        runtime=runtime,
        trace_dir=trace_dir,
        report_dir=report_dir,
    )


def _coerce_verdict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return _invalid_json_verdict(str(value))


def _invalid_json_verdict(raw_output: str) -> dict[str, Any]:
    return {
        "same_function": None,
        "confidence": None,
        "summary": "Agent output was not valid JSON.",
        "matching_evidence": [],
        "difference_evidence": [],
        "noise_assessment": [],
        "raw_output": raw_output,
    }


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
