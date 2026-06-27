from __future__ import annotations

import argparse
import csv
import threading
from concurrent.futures import CancelledError, ThreadPoolExecutor, as_completed
from pathlib import Path
from time import sleep

from enterprise_agent.agents.runtime import AgentRuntime
from experiments.co2full_function_similarity.common.loader import load_co2full_pair_by_row
from experiments.co2full_function_similarity.common.paths import (
    DEFAULT_DB_ROOT,
    DEFAULT_PAIR_CSV,
    REPORT_DIR as DEFAULT_REPORT_DIR,
    TRACE_DIR as DEFAULT_TRACE_DIR,
    report_path_for,
)
from experiments.co2full_function_similarity.common.runner import compare_co2full_row


ROW_START = 0
ROW_LIMIT = 5001
LABEL_1_LIMIT = None
LABEL_0_LIMIT = None
USE_DEEPAGENTS = True
DB_ROOT = DEFAULT_DB_ROOT
CSV_PATH = DEFAULT_PAIR_CSV
TRACE_DIR = DEFAULT_TRACE_DIR
REPORT_DIR = DEFAULT_REPORT_DIR
SKIP_EXISTING = True
STOP_ON_ERROR = False
SLEEP_SECONDS = 0.0
MAX_WORKERS = 32


_THREAD_LOCAL = threading.local()


def main(
    argv: list[str] | None = None,
    *,
    default_trace_dir: str | Path = DEFAULT_TRACE_DIR,
    default_report_dir: str | Path = DEFAULT_REPORT_DIR,
) -> int:
    _apply_args(
        _parse_args(
            argv,
            default_trace_dir=Path(default_trace_dir),
            default_report_dir=Path(default_report_dir),
        )
    )
    row_indices = _select_row_indices()
    pending_rows, prep_fail_count = _select_pending_rows(row_indices)
    ok_count = 0
    fail_count = prep_fail_count
    cancel_count = 0

    print(f"Selected rows: {len(row_indices)}")
    print(f"Pending rows: {len(pending_rows)}")
    if len(pending_rows) <= 20:
        print(f"Pending row indices: {pending_rows}")
    print(f"use_deepagents={USE_DEEPAGENTS}")
    print(f"csv_path={CSV_PATH}")
    print(f"db_root={DB_ROOT}")
    print(f"skip_existing={SKIP_EXISTING}")
    print(f"max_workers={MAX_WORKERS}")

    if MAX_WORKERS <= 1:
        runtime = AgentRuntime(use_deepagents=USE_DEEPAGENTS)
        for row_index in pending_rows:
            try:
                result = compare_co2full_row(
                    row_index=row_index,
                    csv_path=CSV_PATH,
                    db_root=DB_ROOT,
                    runtime=runtime,
                    trace_dir=TRACE_DIR,
                    report_dir=REPORT_DIR,
                )
                ok_count += 1
                _print_ok(row_index=row_index, result=result)
            except Exception as exc:
                fail_count += 1
                print(f"[FAIL] row={row_index} error={exc}")
                if STOP_ON_ERROR:
                    break

            if SLEEP_SECONDS > 0:
                sleep(SLEEP_SECONDS)

        print(f"Done. ok={ok_count} fail={fail_count} cancel={cancel_count}")
        return 0 if fail_count == 0 else 1

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_row = {}
        for row_index in pending_rows:
            future = executor.submit(_run_row, row_index)
            future_to_row[future] = row_index
            if SLEEP_SECONDS > 0:
                sleep(SLEEP_SECONDS)

        stop_requested = False
        for future in as_completed(future_to_row):
            row_index = future_to_row[future]
            if future.cancelled():
                cancel_count += 1
                print(f"[CANCEL] row={row_index}")
                continue

            try:
                result = future.result()
                ok_count += 1
                _print_ok(row_index=row_index, result=result)
            except CancelledError:
                cancel_count += 1
                print(f"[CANCEL] row={row_index}")
            except Exception as exc:
                fail_count += 1
                print(f"[FAIL] row={row_index} error={exc}")
                if STOP_ON_ERROR and not stop_requested:
                    stop_requested = True
                    for pending_future in future_to_row:
                        if pending_future is not future:
                            pending_future.cancel()

    print(f"Done. ok={ok_count} fail={fail_count} cancel={cancel_count}")
    return 0 if fail_count == 0 else 1


def _select_pending_rows(row_indices: list[int]) -> tuple[list[int], int]:
    pending_rows: list[int] = []
    seen_report_paths: set[Path] = set()
    fail_count = 0

    for row_index in row_indices:
        try:
            loaded = load_co2full_pair_by_row(
                row_index=row_index,
                csv_path=CSV_PATH,
                db_root=DB_ROOT,
            )
            pair_key = loaded["source_metadata"]["pair_key"]
            report_path = report_path_for(pair_key, report_dir=REPORT_DIR)
            report_key = report_path.resolve()
        except Exception as exc:
            fail_count += 1
            print(f"[FAIL] row={row_index} error={exc}")
            if STOP_ON_ERROR:
                break
            continue

        if report_key in seen_report_paths:
            print(
                f"[SKIP] row={row_index} pair={pair_key} duplicate_report={report_path.as_posix()}"
            )
            continue
        seen_report_paths.add(report_key)

        if SKIP_EXISTING and report_path.exists():
            print(f"[SKIP] row={row_index} pair={pair_key} report={report_path.as_posix()}")
            continue

        pending_rows.append(row_index)

    return pending_rows, fail_count


def _run_row(row_index: int) -> dict:
    return compare_co2full_row(
        row_index=row_index,
        csv_path=CSV_PATH,
        db_root=DB_ROOT,
        runtime=_get_thread_runtime(),
        trace_dir=TRACE_DIR,
        report_dir=REPORT_DIR,
    )


def _get_thread_runtime() -> AgentRuntime:
    runtime = getattr(_THREAD_LOCAL, "runtime", None)
    if runtime is None:
        runtime = AgentRuntime(use_deepagents=USE_DEEPAGENTS)
        _THREAD_LOCAL.runtime = runtime
    return runtime


def _print_ok(*, row_index: int, result: dict) -> None:
    verdict = result["verdict"]
    print(
        "[OK] "
        f"row={row_index} "
        f"same={verdict.get('same_function')} "
        f"confidence={verdict.get('confidence')} "
        f"parse_status={verdict.get('parse_status', 'n/a')} "
        f"pair={result.get('pair_key')} "
        f"report={result['report_path']}"
    )


def _select_row_indices() -> list[int]:
    if LABEL_1_LIMIT is None and LABEL_0_LIMIT is None:
        return list(range(ROW_START, ROW_START + ROW_LIMIT))

    selected: list[int] = []
    label_counts = {0: 0, 1: 0}
    label_limits = {0: LABEL_0_LIMIT, 1: LABEL_1_LIMIT}
    row_end = ROW_START + ROW_LIMIT

    with Path(CSV_PATH).open("r", encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file)
        for row_index, row in enumerate(reader):
            if row_index < ROW_START:
                continue
            if row_index >= row_end:
                break

            label = _parse_label(row.get("label"))
            if label not in label_limits:
                continue

            limit = label_limits[label]
            if limit is None:
                selected.append(row_index)
                continue
            if label_counts[label] >= limit:
                continue

            selected.append(row_index)
            label_counts[label] += 1

            reached_1 = LABEL_1_LIMIT is None or label_counts[1] >= LABEL_1_LIMIT
            reached_0 = LABEL_0_LIMIT is None or label_counts[0] >= LABEL_0_LIMIT
            if reached_1 and reached_0:
                break

    return selected


def _parse_label(value: str | None) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _parse_args(
    argv: list[str] | None,
    *,
    default_trace_dir: Path,
    default_report_dir: Path,
) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run FuncSim-Agent over a Co2FuLL-style Top-K candidate set."
    )
    parser.add_argument("--csv-path", type=Path, default=DEFAULT_PAIR_CSV)
    parser.add_argument("--db-root", type=Path, default=DEFAULT_DB_ROOT)
    parser.add_argument("--trace-dir", type=Path, default=default_trace_dir)
    parser.add_argument("--report-dir", type=Path, default=default_report_dir)
    parser.add_argument("--row-start", type=int, default=0)
    parser.add_argument("--row-limit", type=int, default=5001)
    parser.add_argument("--label-1-limit", type=int)
    parser.add_argument("--label-0-limit", type=int)
    parser.add_argument("--max-workers", type=int, default=32)
    parser.add_argument("--sleep-seconds", type=float, default=0.0)
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Recompute pairs that already have a report.",
    )
    parser.add_argument("--stop-on-error", action="store_true")
    parser.add_argument(
        "--deterministic-only",
        action="store_true",
        help="Run the local deterministic baseline without calling an LLM.",
    )
    return parser.parse_args(argv)


def _apply_args(args: argparse.Namespace) -> None:
    global CSV_PATH, DB_ROOT, TRACE_DIR, REPORT_DIR
    global ROW_START, ROW_LIMIT, LABEL_1_LIMIT, LABEL_0_LIMIT
    global MAX_WORKERS, SLEEP_SECONDS, SKIP_EXISTING, STOP_ON_ERROR, USE_DEEPAGENTS

    CSV_PATH = args.csv_path
    DB_ROOT = args.db_root
    TRACE_DIR = args.trace_dir
    REPORT_DIR = args.report_dir
    ROW_START = args.row_start
    ROW_LIMIT = args.row_limit
    LABEL_1_LIMIT = args.label_1_limit
    LABEL_0_LIMIT = args.label_0_limit
    MAX_WORKERS = max(1, args.max_workers)
    SLEEP_SECONDS = max(0.0, args.sleep_seconds)
    SKIP_EXISTING = not args.overwrite
    STOP_ON_ERROR = args.stop_on_error
    USE_DEEPAGENTS = not args.deterministic_only


if __name__ == "__main__":
    raise SystemExit(main())
