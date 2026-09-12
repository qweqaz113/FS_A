from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from enterprise_agent.agents.factory import create_function_similarity_package_materializer_agent


EXPERIMENT_DIR = Path(__file__).resolve().parent
RUNS_DIR = EXPERIMENT_DIR / "runs" / "default" / "materializer_runs"


TASK_MESSAGE = """Materialize an improved binary function similarity package.

Use the sandbox filesystem contract exactly:
- Read original materials from /input.
- Use /workspace for all staging, editing, validation, and diffing.
- Write the final complete package to /output only after it is finalized.

Important:
- Treat /input/evolution/parsed_error_records.json as the primary evolution
  record when present.
- Preserve the input package structure where relevant.
- Copy unchanged source/text files too, so /output is a complete package.
- Do not modify /input.
- Do not write outside /workspace and /output.
- Do not leave the final package only in chat.

When finished, briefly report the changed files and confirm /output contains
changelog.md, manifest.json, and diff.md.
"""


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    run_dir = _create_run_dir(args.runs_dir)
    (run_dir / "task_message.md").write_text(TASK_MESSAGE, encoding="utf-8")

    agent = create_function_similarity_package_materializer_agent()
    result = agent.invoke({"messages": [{"role": "user", "content": TASK_MESSAGE}]})

    (run_dir / "agent_result.json").write_text(
        json.dumps(_json_safe(result), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    final_message = _extract_final_text(result)
    (run_dir / "final_message.md").write_text(final_message, encoding="utf-8")

    print(f"[OK] materializer run saved: {run_dir.as_posix()}")
    print("Expected sandbox output: /output")
    return 0


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Materialize an updated FuncSim-Agent package from failure records."
    )
    parser.add_argument("--runs-dir", type=Path, default=RUNS_DIR)
    return parser.parse_args(argv)


def _create_run_dir(runs_dir: Path) -> Path:
    run_id = datetime.now(timezone.utc).strftime("run_%Y%m%dT%H%M%SZ")
    run_dir = runs_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def _extract_final_text(result: Any) -> str:
    if not isinstance(result, dict):
        return str(result)
    messages = result.get("messages", [])
    if not messages:
        return str(result)
    last_message = messages[-1]
    content = (
        last_message.get("content", last_message)
        if isinstance(last_message, dict)
        else getattr(last_message, "content", last_message)
    )
    if isinstance(content, list):
        return "\n".join(str(item) for item in content)
    return str(content)


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if hasattr(value, "model_dump"):
        return _json_safe(value.model_dump())
    if hasattr(value, "dict"):
        return _json_safe(value.dict())
    return str(value)


if __name__ == "__main__":
    raise SystemExit(main())
