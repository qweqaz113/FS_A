from __future__ import annotations

import argparse
import csv
import json
import os
import re
import threading
from concurrent.futures import CancelledError, ThreadPoolExecutor, as_completed
from functools import lru_cache
from pathlib import Path
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_deepseek import ChatDeepSeek

from enterprise_agent.infra.config import load_runtime_env
from experiments.co2full_function_similarity.common.loader import build_code_json_path
from experiments.co2full_function_similarity.common.paths import (
    DATA_DIR,
    DEFAULT_DB_ROOT,
    DEFAULT_PAIR_CSV,
    build_co2full_pair_key,
    result_path_for,
)


DEFAULT_MODEL = "deepseek-v4-flash"
DEFAULT_MAX_WORKERS = 32
DEFAULT_ROW_LIMIT = 5001
DEFAULT_FEW_SHOT_PATH = DEFAULT_DB_ROOT / "few_shot_examples.json"
DEFAULT_REPORT_DIR = DATA_DIR / "co2full_v4_baseline" / "report"

SYSTEM_PROMPT = (
    "You are a helpful, respectful and honest assistant with a deep knowledge of code and "
    "software analysis. Always answer as helpfully as possible, while being safe. Your answers "
    "should not include any harmful, unethical, racist, sexist, toxic, dangerous, or illegal "
    "content. Please ensure that your responses are socially unbiased and positive in nature. "
    "If a question does not make any sense, or is not factually coherent, explain why instead of "
    "answering something not correct. If you don't know the answer to a question, please don't "
    "share false information."
)

FEW_SHOT_PROMPT = """You will be provided with two pseudo code snippets which are extracted from two stripped binaries with different compilation settings (i.e., architecture, compiler, optimization), namely Code A and Code B. Your task is to determine whether the two code snippets are compiled from the same source code. The binaries are stripped so that you can not determine the result based on the different variable names (e.g., v1, v2) and function call names (e.g., sub_893B4).
You answer should return as in the following format: 
<same_source>yes or no</same_source>
<explanation>explanation no more than 150 words</explanation>

Code A: {code_a} 

Code B: {code_b}"""

_SAME_SOURCE_RE = re.compile(
    r"<same_source>\s*(yes|no)\s*</same_source>",
    flags=re.IGNORECASE,
)
_EXPLANATION_RE = re.compile(
    r"<explanation>\s*(.*?)\s*</explanation>",
    flags=re.IGNORECASE | re.DOTALL,
)
_REGISTER_RE = re.compile(r"@<\w+?>")
_INT_RE = re.compile(r"\_\_int\d+")
_THREAD_LOCAL = threading.local()


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    load_runtime_env()
    examples = load_few_shot_examples(args.few_shot_path)
    selected_rows = select_row_indices(
        csv_path=args.csv_path,
        row_start=args.row_start,
        row_limit=args.row_limit,
        label_1_limit=args.label_1_limit,
        label_0_limit=args.label_0_limit,
    )
    pending_rows, invalid_rows = select_pending_rows(
        selected_rows,
        csv_path=args.csv_path,
        db_root=args.db_root,
        report_dir=args.report_dir,
        overwrite=args.overwrite,
    )

    print(f"Selected rows: {len(selected_rows)}")
    print(f"Invalid rows (empty or unavailable pseudocode): {len(invalid_rows)}")
    print(f"Pending rows: {len(pending_rows)}")
    print(f"model={args.model}")
    print("temperature=0 top_p=1.0")
    print(f"max_workers={args.max_workers}")
    print(f"csv_path={args.csv_path.resolve()}")
    print(f"db_root={args.db_root.resolve()}")
    print(f"few_shot_path={args.few_shot_path.resolve()}")
    print(f"report_dir={args.report_dir.resolve()}")

    if args.dry_run:
        if invalid_rows:
            print(f"Invalid row indices: {[item['row_index'] for item in invalid_rows]}")
        print("Dry run complete; no API requests were sent and no reports were written.")
        return 0

    if not os.getenv("DEEPSEEK_API_KEY"):
        raise RuntimeError("DEEPSEEK_API_KEY is not configured in the environment or .env file.")

    args.report_dir.mkdir(parents=True, exist_ok=True)
    invalid_path = args.report_dir.parent / "invalid_rows.json"
    invalid_path.write_text(
        json.dumps(invalid_rows, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    ok_count = 0
    fail_count = 0
    cancel_count = 0
    with ThreadPoolExecutor(max_workers=max(1, args.max_workers)) as executor:
        future_to_row = {
            executor.submit(run_row, row_index, args, examples): row_index
            for row_index in pending_rows
        }
        stop_requested = False
        for future in as_completed(future_to_row):
            row_index = future_to_row[future]
            if future.cancelled():
                cancel_count += 1
                print(f"[CANCEL] row={row_index}")
                continue
            try:
                report = future.result()
                ok_count += 1
                print(
                    f"[OK] row={row_index} same={report['same_function']} "
                    f"parse_status={report['parse_status']} pair={report['pair_key']}"
                )
            except CancelledError:
                cancel_count += 1
                print(f"[CANCEL] row={row_index}")
            except Exception as exc:
                fail_count += 1
                print(f"[FAIL] row={row_index} error={exc}")
                if args.stop_on_error and not stop_requested:
                    stop_requested = True
                    for pending_future in future_to_row:
                        if pending_future is not future:
                            pending_future.cancel()

    print(f"Done. ok={ok_count} fail={fail_count} cancel={cancel_count}")
    return 0 if fail_count == 0 else 1


def load_few_shot_examples(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8") as file:
        raw_examples = json.load(file)
    if not isinstance(raw_examples, list) or not raw_examples:
        raise ValueError(f"Few-shot example file is empty or invalid: {path}")
    examples: list[dict[str, str]] = []
    for index, item in enumerate(raw_examples):
        if not isinstance(item, dict) or not item.get("content") or not item.get("reply"):
            raise ValueError(f"Few-shot example {index} must contain content and reply fields.")
        examples.append({"content": str(item["content"]), "reply": str(item["reply"])})
    return examples


def build_messages(
    *,
    code_a: str,
    code_b: str,
    examples: list[dict[str, str]],
) -> list[SystemMessage | HumanMessage | AIMessage]:
    messages: list[SystemMessage | HumanMessage | AIMessage] = [
        SystemMessage(content=SYSTEM_PROMPT)
    ]
    for example in examples:
        messages.append(HumanMessage(content=example["content"]))
        messages.append(AIMessage(content=example["reply"]))
    messages.append(HumanMessage(content=FEW_SHOT_PROMPT.format(code_a=code_a, code_b=code_b)))
    return messages


def parse_response(raw_output: str) -> dict[str, Any]:
    label_match = _SAME_SOURCE_RE.search(raw_output)
    explanation_match = _EXPLANATION_RE.search(raw_output)
    if label_match is None:
        return {
            "same_function": None,
            "summary": explanation_match.group(1).strip() if explanation_match else "",
            "parse_status": "invalid_missing_same_source",
        }
    return {
        "same_function": label_match.group(1).lower() == "yes",
        "summary": explanation_match.group(1).strip() if explanation_match else "",
        "parse_status": "ok" if explanation_match else "ok_missing_explanation",
    }


def run_row(
    row_index: int,
    args: argparse.Namespace,
    examples: list[dict[str, str]],
) -> dict[str, Any]:
    loaded = load_baseline_pair_by_row(
        row_index=row_index,
        csv_path=args.csv_path,
        db_root=args.db_root,
    )
    source = loaded["source_metadata"]
    pair_key = source["pair_key"]
    response = get_thread_model(args.model).invoke(
        build_messages(code_a=loaded["code_a"], code_b=loaded["code_b"], examples=examples)
    )
    raw_output = response.content if isinstance(response.content, str) else str(response.content)
    parsed = parse_response(raw_output)
    report = {
        "pair_key": pair_key,
        "same_function": parsed["same_function"],
        "confidence": None,
        "summary": parsed["summary"],
        "parse_status": parsed["parse_status"],
        "raw_output": raw_output,
        "source": source,
        "model": args.model,
        "prompt": "co2full_few_shot",
        "temperature": 0,
        "top_p": 1.0,
    }
    report_path = result_path_for(pair_key, args.report_dir)
    temporary_path = report_path.with_suffix(report_path.suffix + ".tmp")
    temporary_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary_path.replace(report_path)
    return report


def get_thread_model(model_name: str) -> ChatDeepSeek:
    model = getattr(_THREAD_LOCAL, "model", None)
    cached_name = getattr(_THREAD_LOCAL, "model_name", None)
    if model is None or cached_name != model_name:
        model = ChatDeepSeek(
            model=model_name,
            api_key=os.environ["DEEPSEEK_API_KEY"],
            temperature=0,
            top_p=1.0,
            timeout=600,
            max_retries=3,
        )
        _THREAD_LOCAL.model = model
        _THREAD_LOCAL.model_name = model_name
    return model


def load_baseline_pair_by_row(
    *,
    row_index: int,
    csv_path: Path,
    db_root: Path,
) -> dict[str, Any]:
    rows = _read_csv_rows(str(csv_path.resolve()))
    if row_index < 0 or row_index >= len(rows):
        raise IndexError(f"CSV row index out of range: {row_index}")
    row = rows[row_index]
    code_a = load_baseline_pseudocode(db_root, row["bin_name_1"], row["fva_1"])
    code_b = load_baseline_pseudocode(db_root, row["bin_name_2"], row["fva_2"])
    pair_key = build_co2full_pair_key(
        bin_name_1=row["bin_name_1"],
        fva_1=row["fva_1"],
        bin_name_2=row["bin_name_2"],
        fva_2=row["fva_2"],
    )
    return {
        "code_a": code_a,
        "code_b": code_b,
        "source_metadata": {
            "type": "co2full_baseline_row",
            "csv_path": csv_path.resolve().as_posix(),
            "row_index": row_index,
            "label": _parse_label(row.get("label")),
            "bin_name_1": row["bin_name_1"],
            "fva_1": row["fva_1"],
            "bin_name_2": row["bin_name_2"],
            "fva_2": row["fva_2"],
            "func_name_1": row.get("func_name_1"),
            "func_name_2": row.get("func_name_2"),
            "db_type": row.get("db_type"),
            "pair_key": pair_key,
            "csv_key_pair": row.get("key_pair"),
            "is_code_A_empty": code_a == "",
            "is_code_B_empty": code_b == "",
        },
    }


def load_baseline_pseudocode(db_root: Path, bin_name: str, fva: str) -> str:
    json_path = build_code_json_path(db_root, bin_name).resolve()
    data = _read_code_json(str(json_path))
    code_info = None
    for key in (fva, fva.lower(), fva.upper()):
        if key in data:
            code_info = data[key]
            break
    if code_info is None:
        raise KeyError(f"Function address {fva} not found in {json_path}")
    pseudo_code = str(code_info.get("pseudo_code") or "")
    if not pseudo_code:
        raise ValueError(f"Pseudocode is empty for {bin_name}@{fva}")
    return clean_pseudo_code(pseudo_code)


def clean_pseudo_code(pseudo_code: str) -> str:
    """Match Co2FuLL's original pseudocode normalization."""
    code_lines: list[str] = []
    is_content = False
    for index, line in enumerate(pseudo_code.split("\n")):
        if "//" in line and index == 0:
            continue
        if "(" in line and index <= 1:
            code_lines.append(_INT_RE.sub("int", _REGISTER_RE.sub("", line)))
            continue
        if line == "{":
            code_lines.append(line)
            continue
        if line == "":
            is_content = True
        if not is_content:
            code_lines.append(_INT_RE.sub("int", line).split("//")[0])
        else:
            code_lines.append(line)
    return "\n".join(code_lines)


@lru_cache(maxsize=4)
def _read_csv_rows(csv_path: str) -> tuple[dict[str, str], ...]:
    with Path(csv_path).open("r", encoding="utf-8", newline="") as file:
        return tuple(dict(row) for row in csv.DictReader(file))


@lru_cache(maxsize=None)
def _read_code_json(json_path: str) -> dict[str, dict[str, Any]]:
    with Path(json_path).open("r", encoding="utf-8") as file:
        return json.load(file)


def select_pending_rows(
    row_indices: list[int],
    *,
    csv_path: Path,
    db_root: Path,
    report_dir: Path,
    overwrite: bool,
) -> tuple[list[int], list[dict[str, Any]]]:
    pending: list[int] = []
    invalid: list[dict[str, Any]] = []
    for row_index in row_indices:
        try:
            loaded = load_baseline_pair_by_row(
                row_index=row_index,
                csv_path=csv_path,
                db_root=db_root,
            )
        except (KeyError, OSError, ValueError) as exc:
            invalid.append({"row_index": row_index, "error": str(exc)})
            continue
        pair_key = loaded["source_metadata"]["pair_key"]
        report_path = result_path_for(pair_key, report_dir)
        if not overwrite and report_path.exists():
            continue
        pending.append(row_index)
    return pending, invalid


def select_row_indices(
    *,
    csv_path: Path,
    row_start: int,
    row_limit: int,
    label_1_limit: int | None,
    label_0_limit: int | None,
) -> list[int]:
    selected: list[int] = []
    label_counts = {0: 0, 1: 0}
    label_limits = {0: label_0_limit, 1: label_1_limit}
    row_end = row_start + row_limit
    with csv_path.open("r", encoding="utf-8", newline="") as file:
        for row_index, row in enumerate(csv.DictReader(file)):
            if row_index < row_start:
                continue
            if row_index >= row_end:
                break
            label = _parse_label(row.get("label"))
            if label not in (0, 1):
                continue
            limit = label_limits[label]
            if limit is not None and label_counts[label] >= limit:
                continue
            selected.append(row_index)
            label_counts[label] += 1
            if label_1_limit is not None or label_0_limit is not None:
                reached_1 = label_1_limit is None or label_counts[1] >= label_1_limit
                reached_0 = label_0_limit is None or label_counts[0] >= label_0_limit
                if reached_1 and reached_0:
                    break
    return selected


def _parse_label(value: str | None) -> int | None:
    try:
        return int(value) if value not in (None, "") else None
    except ValueError:
        return None


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the original Co2FuLL Few-Shot verifier with DeepSeek V4."
    )
    parser.add_argument("--csv-path", type=Path, default=DEFAULT_PAIR_CSV)
    parser.add_argument("--db-root", type=Path, default=DEFAULT_DB_ROOT)
    parser.add_argument("--few-shot-path", type=Path, default=DEFAULT_FEW_SHOT_PATH)
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--row-start", type=int, default=0)
    parser.add_argument("--row-limit", type=int, default=DEFAULT_ROW_LIMIT)
    parser.add_argument("--label-1-limit", type=int)
    parser.add_argument("--label-0-limit", type=int)
    parser.add_argument("--max-workers", type=int, default=DEFAULT_MAX_WORKERS)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--stop-on-error", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
