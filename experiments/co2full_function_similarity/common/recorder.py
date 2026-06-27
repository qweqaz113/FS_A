from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from enterprise_agent.domain.function_similarity import FunctionCompareInput, FunctionCompareVerdict
from experiments.co2full_function_similarity.common.paths import (
    REPORT_DIR,
    TRACE_DIR,
    pair_key_from_metadata,
    report_path_for,
    trace_path_for,
)


def new_trace_id(prefix: str = "cmp") -> str:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"{prefix}_{timestamp}_{uuid.uuid4().hex[:8]}"


@dataclass
class ExperimentRecorder:
    trace_id: str
    trace_path: Path
    report_path: Path
    created_at: str
    pair_key: str | None = None
    source: dict[str, Any] | None = None
    input: dict[str, Any] | None = None
    agent_result: Any | None = None
    verdict: dict[str, Any] | None = None
    errors: list[str] = field(default_factory=list)

    @classmethod
    def start(
        cls,
        *,
        compare_input: FunctionCompareInput | None = None,
        source_metadata: dict[str, Any] | None = None,
        trace_dir: str | Path = TRACE_DIR,
        report_dir: str | Path = REPORT_DIR,
    ) -> "ExperimentRecorder":
        trace_id = new_trace_id()
        pair_key = pair_key_from_metadata(source_metadata)
        file_stem = pair_key or trace_id
        recorder = cls(
            trace_id=trace_id,
            trace_path=trace_path_for(file_stem, trace_dir=trace_dir),
            report_path=report_path_for(file_stem, report_dir=report_dir),
            created_at=datetime.now(UTC).isoformat(),
            pair_key=pair_key,
            source=_json_safe(source_metadata) if source_metadata else None,
        )
        if compare_input is not None:
            recorder.record_input(compare_input)
        return recorder

    def record_input(self, compare_input: FunctionCompareInput) -> None:
        self.input = compare_input.to_dict()

    def record_agent_result(self, result: Any) -> None:
        self.agent_result = _json_safe(result)

    def record_verdict(self, verdict: FunctionCompareVerdict | dict[str, Any]) -> None:
        if isinstance(verdict, FunctionCompareVerdict):
            self.verdict = verdict.to_dict()
            return
        self.verdict = _json_safe(verdict)

    def record_error(self, error: Exception | str) -> None:
        self.errors.append(str(error))

    def save_trace(self) -> Path:
        self.trace_path.parent.mkdir(parents=True, exist_ok=True)
        payload = asdict(self)
        payload["trace_path"] = self.trace_path.as_posix()
        payload["report_path"] = self.report_path.as_posix()
        self.trace_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return self.trace_path

    def save_report(self) -> Path:
        self.report_path.parent.mkdir(parents=True, exist_ok=True)
        payload: dict[str, Any] = {
            "trace_id": self.trace_id,
            "trace_path": self.trace_path.as_posix(),
            "report_path": self.report_path.as_posix(),
        }
        if self.pair_key:
            payload["pair_key"] = self.pair_key
        if self.source:
            payload["source"] = self.source
        if self.errors:
            payload["errors"] = self.errors
        if self.verdict:
            payload.update(self.verdict)

        self.report_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return self.report_path

    def save_all(self) -> tuple[Path, Path]:
        trace_path = self.save_trace()
        report_path = self.save_report()
        return trace_path, report_path


def _json_safe(value: Any) -> Any:
    try:
        json.dumps(value, ensure_ascii=False)
        return value
    except TypeError:
        if hasattr(value, "model_dump"):
            return _json_safe(value.model_dump())
        if isinstance(value, dict):
            return {str(key): _json_safe(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [_json_safe(item) for item in value]
        return repr(value)
