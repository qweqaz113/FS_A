from __future__ import annotations

import argparse
import csv
import threading
from concurrent.futures import CancelledError, ThreadPoolExecutor, as_completed
from pathlib import Path
from time import sleep

from enterprise_agent.agents.runtime import AgentRuntime
from experiments.co2full_function_similarity.paths import (
    DATA_DIR,
    DEFAULT_DB_ROOT,
    DEFAULT_PAIR_CSV,
)
from experiments.co2full_function_similarity.runner import compare_co2full_row


CSV_PATH = DEFAULT_PAIR_CSV
DB_ROOT = DEFAULT_DB_ROOT
ERRORS_CSV = DATA_DIR / "refine_eval" / "errors.csv"
TRACE_DIR = DATA_DIR / "refine_error_rerun" / "trace"
REPORT_DIR = DATA_DIR / "refine_error_rerun" / "report"
USE_DEEPAGENTS = True
MAX_WORKERS = 32
SLEEP_SECONDS = 0.0
STOP_ON_ERROR = False
ROW_INDEX_LIMIT = 500

_THREAD_LOCAL = threading.local()


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    row_indices = _load_error_row_indices(
        Path(args.errors_csv), row_index_limit=args.row_index_limit
    )
    row_indices = _dedupe_preserve_order(row_indices)

    ok_count = 0
    fail_count = 0
    cancel_count = 0

    print(f"Rows to rerun: {row_indices}")
    print(f"errors_csv={args.errors_csv}")
    print(f"csv_path={args.csv_path}")
    print(f"db_root={args.db_root}")
    print(f"trace_dir={args.trace_dir}")
    print(f"report_dir={args.report_dir}")
    print(f"max_workers={args.max_workers}")
    print(f"row_index_limit={args.row_index_limit}")

    if args.dry_run:
        return 0

    if args.max_workers <= 1:
        runtime = AgentRuntime(use_deepagents=USE_DEEPAGENTS)
        for row_index in row_indices:
            try:
                result = _run_row(
                    row_index,
                    runtime=runtime,
                    csv_path=args.csv_path,
                    db_root=args.db_root,
                    trace_dir=args.trace_dir,
                    report_dir=args.report_dir,
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

    with ThreadPoolExecutor(max_workers=args.max_workers) as executor:
        future_to_row = {
            executor.submit(
                _run_row,
                row_index,
                csv_path=args.csv_path,
                db_root=args.db_root,
                trace_dir=args.trace_dir,
                report_dir=args.report_dir,
            ): row_index
            for row_index in row_indices
        }

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

    print(f"Done. ok={ok_count} fail={fail_count} cancel={cancel_count}")
    return 0 if fail_count == 0 else 1


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Rerun errors from refine_eval/errors.csv whose row_index is within the first N rows."
    )
    parser.add_argument("--errors-csv", type=Path, default=ERRORS_CSV)
    parser.add_argument("--csv-path", type=Path, default=CSV_PATH)
    parser.add_argument("--db-root", type=Path, default=DB_ROOT)
    parser.add_argument("--trace-dir", type=Path, default=TRACE_DIR)
    parser.add_argument("--report-dir", type=Path, default=REPORT_DIR)
    parser.add_argument("--max-workers", type=int, default=MAX_WORKERS)
    parser.add_argument("--row-index-limit", type=int, default=ROW_INDEX_LIMIT)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def _load_error_row_indices(path: Path, *, row_index_limit: int) -> list[int]:
    with path.open("r", encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file)
        row_indices = []
        for row in reader:
            if not row.get("row_index"):
                continue
            row_index = int(row["row_index"])
            if row_index < row_index_limit:
                row_indices.append(row_index)
        return row_indices


def _dedupe_preserve_order(values: list[int]) -> list[int]:
    seen: set[int] = set()
    result: list[int] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _run_row(
    row_index: int,
    *,
    csv_path: str,
    db_root: str,
    trace_dir: str,
    report_dir: str,
    runtime: AgentRuntime | None = None,
) -> dict:
    return compare_co2full_row(
        row_index=row_index,
        csv_path=csv_path,
        db_root=db_root,
        runtime=runtime or _get_thread_runtime(),
        trace_dir=trace_dir,
        report_dir=report_dir,
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


if __name__ == "__main__":
    raise SystemExit(main())
