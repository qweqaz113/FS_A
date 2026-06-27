from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from enterprise_agent.agents.factory import create_function_similarity_error_analysis_agent
from experiments.co2full_function_similarity.loader import load_co2full_pair_by_row
from experiments.co2full_function_similarity.paths import safe_result_filename


EXPERIMENT_DIR = Path(__file__).resolve().parents[1]
REPORT_DIR = EXPERIMENT_DIR / "data/report"
TRACE_DIR = EXPERIMENT_DIR / "data/trace"
DB_ROOT = EXPERIMENT_DIR / "data/dbs"
CSV_PATH = EXPERIMENT_DIR / "data/dbs/xm-full_top5-250515.csv"
OUTPUT_DIR = EXPERIMENT_DIR / "data/skill_evolution/error_analysis"
MAX_CASE_DIR_NAME = 96
LIMIT = None
OVERWRITE = False


def main(argv: list[str] | None = None) -> int:
    _apply_args(_parse_args(argv))
    report_dir = Path(REPORT_DIR)
    output_dir = Path(OUTPUT_DIR)
    output_dir.mkdir(parents=True, exist_ok=True)

    cases = list(_iter_failure_cases(report_dir))
    if LIMIT is not None:
        cases = cases[:LIMIT]

    print(f"Failure cases selected: {len(cases)}")
    print(f"report_dir={report_dir.as_posix()}")
    print(f"trace_dir={Path(TRACE_DIR).as_posix()}")
    print(f"output_dir={output_dir.as_posix()}")

    if not cases:
        return 0

    agent = create_function_similarity_error_analysis_agent()
    parsed_records: list[dict[str, Any]] = []

    for case in cases:
        pair_key = case["pair_key"]
        case_dir = _case_dir_for(output_dir, pair_key)
        report_path = case_dir / "analysis_report.md"
        parsed_path = case_dir / "parsed_error_record.json"
        agent_result_path = case_dir / "agent_result.json"

        if report_path.exists() and parsed_path.exists() and not OVERWRITE:
            existing_record = _load_json(parsed_path)
            if existing_record.get("items"):
                print(f"[SKIP] pair={pair_key} analysis={report_path.as_posix()}")
                parsed_records.append(existing_record)
                continue
            print(f"[RERUN] pair={pair_key} previous analysis parsed 0 items")

        case_dir.mkdir(parents=True, exist_ok=True)
        prompt_payload = _build_prompt_payload(case)
        (case_dir / "analysis_input.json").write_text(
            json.dumps(prompt_payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        result = agent.invoke(
            {"messages": [{"role": "user", "content": _format_user_message(prompt_payload)}]}
        )
        agent_result_path.write_text(
            json.dumps(_json_safe(result), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        analysis_text = _extract_final_text(result)
        report_path.write_text(analysis_text, encoding="utf-8")

        parsed_record = {
            "instance_id": pair_key,
            "source_file": report_path.name,
            "failure_type": case["failure_type"],
            "label": case["label"],
            "prediction": case["prediction"],
            "report_path": case["report_path"].as_posix(),
            "trace_path": case["trace_path"].as_posix() if case["trace_path"] else None,
            "items": _parse_failure_items(analysis_text),
        }
        parsed_path.write_text(
            json.dumps(parsed_record, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        parsed_records.append(parsed_record)
        if not parsed_record["items"]:
            print(f"[WARN] parsed 0 items pair={pair_key} report={report_path.as_posix()}")
        print(
            f"[OK] type={case['failure_type']} items={len(parsed_record['items'])} pair={pair_key}"
        )

    aggregate_path = output_dir / "parsed_error_records.json"
    aggregate_path.write_text(
        json.dumps(parsed_records, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Aggregate records: {aggregate_path.as_posix()}")
    return 0


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyze misclassified FuncSim-Agent reports and extract reusable lessons."
    )
    parser.add_argument("--report-dir", type=Path, default=REPORT_DIR)
    parser.add_argument("--trace-dir", type=Path, default=TRACE_DIR)
    parser.add_argument("--db-root", type=Path, default=DB_ROOT)
    parser.add_argument("--csv-path", type=Path, default=CSV_PATH)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args(argv)


def _apply_args(args: argparse.Namespace) -> None:
    global REPORT_DIR, TRACE_DIR, DB_ROOT, CSV_PATH, OUTPUT_DIR, LIMIT, OVERWRITE

    REPORT_DIR = args.report_dir
    TRACE_DIR = args.trace_dir
    DB_ROOT = args.db_root
    CSV_PATH = args.csv_path
    OUTPUT_DIR = args.output_dir
    LIMIT = args.limit
    OVERWRITE = args.overwrite


def _case_dir_for(output_dir: Path, pair_key: str) -> Path:
    legacy_name = Path(safe_result_filename(pair_key)).stem
    legacy_dir = output_dir / legacy_name
    if legacy_dir.exists():
        return legacy_dir

    safe_name = _short_case_dir_name(pair_key)
    return output_dir / safe_name


def _short_case_dir_name(pair_key: str) -> str:
    safe_name = Path(safe_result_filename(pair_key)).stem
    digest = hashlib.sha1(pair_key.encode("utf-8")).hexdigest()[:12]
    suffix = f"-{digest}"
    max_prefix_len = MAX_CASE_DIR_NAME - len(suffix)
    if len(safe_name) <= MAX_CASE_DIR_NAME:
        return safe_name
    return f"{safe_name[:max_prefix_len].rstrip(' ._-')}{suffix}"


def _iter_failure_cases(report_dir: Path) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for report_path in sorted(report_dir.glob("*.json")):
        report = _load_json(report_path)
        source = report.get("source") or {}
        label = source.get("label")
        prediction = report.get("same_function")

        if label not in (0, 1) or not isinstance(prediction, bool):
            continue

        expected = label == 1
        if prediction == expected:
            continue

        pair_key = report.get("pair_key") or source.get("pair_key") or report_path.stem
        trace_path = Path(TRACE_DIR) / report_path.name
        cases.append(
            {
                "pair_key": str(pair_key),
                "failure_type": "false_negative" if expected else "false_positive",
                "label": label,
                "prediction": prediction,
                "report": report,
                "report_path": report_path,
                "trace": _load_json(trace_path) if trace_path.exists() else None,
                "trace_path": trace_path if trace_path.exists() else None,
                "source": source,
            }
        )
    return cases


def _build_prompt_payload(case: dict[str, Any]) -> dict[str, Any]:
    source = case["source"]
    row_index = source.get("row_index")
    code_a = ""
    code_b = ""
    if row_index is not None:
        loaded = load_co2full_pair_by_row(
            row_index=int(row_index),
            csv_path=CSV_PATH,
            db_root=DB_ROOT,
        )
        compare_input = loaded["compare_input"]
        code_a = compare_input.code_a
        code_b = compare_input.code_b

    return {
        "pair_key": case["pair_key"],
        "failure_type": case["failure_type"],
        "label": case["label"],
        "prediction": case["prediction"],
        "source": source,
        "codea": code_a,
        "codeb": code_b,
        "report": case["report"],
        "trace": case["trace"],
    }


def _format_user_message(payload: dict[str, Any]) -> str:
    return (
        "Analyze this failed binary function similarity judgment.\n\n"
        f"pair_key: {payload['pair_key']}\n"
        f"failure_type: {payload['failure_type']}\n"
        f"label: {payload['label']}\n"
        f"prediction: {payload['prediction']}\n\n"
        "codea:\n"
        f"{payload['codea']}\n\n"
        "codeb:\n"
        f"{payload['codeb']}\n\n"
        "report JSON:\n"
        f"{json.dumps(payload['report'], ensure_ascii=False, indent=2)}\n\n"
        "trace JSON:\n"
        f"{json.dumps(payload['trace'], ensure_ascii=False, indent=2)}"
        "\n\nSTRICTLY follow the system prompt required workflow.\n"
        "Produce ONLY the Failure Cause Item and Failure Memory Item sections.\n"
        'Do NOT summarize. Do NOT say "the analysis above".\n'
        "Do NOT wrap the answer in code fences.\n"
    )


_ITEM_HEADING_RE = re.compile(
    r"^#\s+(Failure Cause Item|Failure Memory Item)\s+(\d+)\s*\n"
    r"(.*?)(?=\n#\s+(?:Failure Cause Item|Failure Memory Item)\s+\d+|\Z)",
    re.MULTILINE | re.DOTALL,
)
_SECTION_RE = re.compile(
    r"^##\s+{name}\s*\n(.*?)(?=\n##\s+|\Z)",
    re.MULTILINE | re.DOTALL,
)


def _parse_failure_items(text: str) -> list[dict[str, Any]]:
    stripped = _strip_code_fences(_strip_think_prefix(text))
    items: list[dict[str, Any]] = []
    for match in _ITEM_HEADING_RE.finditer(stripped):
        raw_type = match.group(1)
        body = match.group(3).strip()
        item_type = "failure_cause" if raw_type == "Failure Cause Item" else "failure_memory"
        item = {
            "type": item_type,
            "number": int(match.group(2)),
            "title": _extract_section(body, "Title"),
            "description": _extract_section(body, "Description"),
            "content": _extract_section(body, "Content"),
        }
        if item_type == "failure_cause":
            item["relation_to_skill"] = _extract_section(body, "Relation to Skill")
        else:
            item["skill_reflection"] = _extract_section(body, "Skill Reflection")
        items.append(item)
    return items


def _extract_section(body: str, name: str) -> str:
    pattern = _SECTION_RE.pattern.format(name=re.escape(name))
    match = re.search(pattern, body, re.MULTILINE | re.DOTALL)
    return match.group(1).strip() if match else ""


def _strip_code_fences(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```") and stripped.endswith("```"):
        stripped = re.sub(r"^```\w*\n?", "", stripped)
        stripped = re.sub(r"\n?```$", "", stripped)
    return stripped


def _strip_think_prefix(text: str) -> str:
    if "</think>" not in text:
        return text
    return text.rsplit("</think>", 1)[-1]


def _extract_final_text(result: Any) -> str:
    if not isinstance(result, dict):
        return str(result)
    messages = result.get("messages", [])
    if not messages:
        return str(result)
    assistant_texts = [
        _message_content_to_text(message)
        for message in messages
        if _message_role(message) == "assistant"
    ]
    for text in reversed(assistant_texts):
        if "# Failure Cause Item" in text:
            return text
    if assistant_texts:
        return assistant_texts[-1]
    return _message_content_to_text(messages[-1])


def _message_role(message: Any) -> str | None:
    if isinstance(message, dict):
        return message.get("role")
    return getattr(message, "type", None) or getattr(message, "role", None)


def _message_content_to_text(message: Any) -> str:
    content = (
        message.get("content", message)
        if isinstance(message, dict)
        else getattr(message, "content", message)
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


def _load_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


if __name__ == "__main__":
    raise SystemExit(main())
