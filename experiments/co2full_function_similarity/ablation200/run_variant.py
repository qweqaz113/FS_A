from __future__ import annotations

import argparse
import json
import threading
from concurrent.futures import CancelledError, ThreadPoolExecutor, as_completed
from pathlib import Path
from time import sleep
from typing import Any

from experiments.co2full_function_similarity.ablation200.common import (
    ABLATION_DIR,
    CSV_PATH,
    DB_ROOT,
    load_subset,
)

from deepagents import create_deep_agent
from enterprise_agent.agents.backends.sandbox import build_sandbox_backend
from enterprise_agent.agents.factory import create_enterprise_agent
from enterprise_agent.agents.prompts import load_prompt
from enterprise_agent.agents.runtime import AgentRuntime
from enterprise_agent.agents.subagents.decompiler_noise_analyst import (
    build_decompiler_noise_analyst_subagent,
)
from enterprise_agent.agents.subagents.difference_analyst import build_difference_analyst_subagent
from enterprise_agent.agents.subagents.semantic_analyst import build_semantic_analyst_subagent
from enterprise_agent.agents.tools.registry import build_tools
from enterprise_agent.infra.config import get_settings
from experiments.co2full_function_similarity.runner import compare_co2full_row


VARIANTS = {
    "single_agent",
    "wo_diffprobe",
    "wo_noiselens",
    "full_refined_rerun",
}
DEFAULT_MAX_WORKERS = 32
SLEEP_SECONDS = 0.0
USE_DEEPAGENTS = True

_THREAD_LOCAL = threading.local()


class AblationRuntime(AgentRuntime):
    def __init__(self, *, variant: str):
        super().__init__(use_deepagents=USE_DEEPAGENTS)
        self.variant = variant

    def _get_agent(self) -> Any:
        if self._agent is None:
            self._agent = create_ablation_agent(self.variant)
        return self._agent


def main() -> int:
    args = parse_args()
    subset_row_indices = [int(row["row_index"]) for row in load_subset(Path(args.subset_csv))]
    subset_row_indices = dedupe_preserve_order(subset_row_indices)

    trace_dir = Path(args.output_root) / args.variant / "trace"
    report_dir = Path(args.output_root) / args.variant / "report"
    completed_row_indices = load_completed_row_indices(report_dir)
    if args.force:
        row_indices = subset_row_indices
    else:
        row_indices = [
            row_index for row_index in subset_row_indices if row_index not in completed_row_indices
        ]

    print(f"variant={args.variant}")
    print(f"subset_rows={len(subset_row_indices)}")
    print(f"completed_rows={len(completed_row_indices)}")
    print(f"rows_to_run={len(row_indices)}")
    print(f"trace_dir={trace_dir}")
    print(f"report_dir={report_dir}")
    print(f"max_workers={args.max_workers}")
    print(f"force={args.force}")
    print(f"row_indices={row_indices}")

    if args.dry_run:
        return 0

    trace_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)

    if not row_indices:
        print("Nothing to run. All subset rows already have reports.")
        return 0

    ok_count = 0
    fail_count = 0
    cancel_count = 0

    if args.max_workers <= 1:
        runtime = AblationRuntime(variant=args.variant)
        for row_index in row_indices:
            try:
                result = run_row(
                    row_index,
                    variant=args.variant,
                    runtime=runtime,
                    trace_dir=trace_dir,
                    report_dir=report_dir,
                )
                ok_count += 1
                print_ok(row_index=row_index, result=result)
            except Exception as exc:
                fail_count += 1
                print(f"[FAIL] row={row_index} error={exc}")
            if SLEEP_SECONDS > 0:
                sleep(SLEEP_SECONDS)
        print(f"Done. ok={ok_count} fail={fail_count} cancel={cancel_count}")
        return 0 if fail_count == 0 else 1

    with ThreadPoolExecutor(max_workers=args.max_workers) as executor:
        future_to_row = {
            executor.submit(
                run_row,
                row_index,
                variant=args.variant,
                trace_dir=trace_dir,
                report_dir=report_dir,
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
                print_ok(row_index=row_index, result=result)
            except CancelledError:
                cancel_count += 1
                print(f"[CANCEL] row={row_index}")
            except Exception as exc:
                fail_count += 1
                print(f"[FAIL] row={row_index} error={exc}")

    print(f"Done. ok={ok_count} fail={fail_count} cancel={cancel_count}")
    return 0 if fail_count == 0 else 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run one 200-pair ablation variant.")
    parser.add_argument("--variant", required=True, choices=sorted(VARIANTS))
    parser.add_argument("--subset-csv", default=ABLATION_DIR / "subset.csv")
    parser.add_argument("--output-root", default=ABLATION_DIR)
    parser.add_argument("--max-workers", type=int, default=DEFAULT_MAX_WORKERS)
    parser.add_argument(
        "--force",
        action="store_true",
        help="Rerun rows even when an existing report for that row_index is present.",
    )
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def load_completed_row_indices(report_dir: Path) -> set[int]:
    completed: set[int] = set()
    if not report_dir.exists():
        return completed
    for path in report_dir.glob("*.json"):
        try:
            report = json.loads(path.read_text(encoding="utf-8"))
            row_index = report.get("source", {}).get("row_index")
            if row_index is not None:
                completed.add(int(row_index))
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            continue
    return completed


def run_row(
    row_index: int,
    *,
    variant: str,
    trace_dir: Path,
    report_dir: Path,
    runtime: AgentRuntime | None = None,
) -> dict[str, Any]:
    return compare_co2full_row(
        row_index=row_index,
        csv_path=CSV_PATH,
        db_root=DB_ROOT,
        runtime=runtime or get_thread_runtime(variant),
        trace_dir=trace_dir,
        report_dir=report_dir,
    )


def get_thread_runtime(variant: str) -> AgentRuntime:
    runtimes = getattr(_THREAD_LOCAL, "runtimes", None)
    if runtimes is None:
        runtimes = {}
        _THREAD_LOCAL.runtimes = runtimes
    if variant not in runtimes:
        runtimes[variant] = AblationRuntime(variant=variant)
    return runtimes[variant]


def create_ablation_agent(variant: str) -> Any:
    if variant == "full_refined_rerun":
        return create_enterprise_agent()

    settings = get_settings()
    sandbox_backend = build_sandbox_backend(settings)
    subagents = build_variant_subagents(variant)
    return create_deep_agent(
        tools=build_tools(),
        system_prompt=variant_system_prompt(variant),
        model=settings.llm_model,
        backend=sandbox_backend,
        subagents=subagents,
        skills=[settings.sandbox_skills_dir],
    )


def build_variant_subagents(variant: str) -> list[dict[str, str]]:
    if variant == "single_agent":
        return []

    subagents = [build_semantic_analyst_subagent()]
    if variant != "wo_diffprobe":
        subagents.append(build_difference_analyst_subagent())
    if variant != "wo_noiselens":
        subagents.append(build_decompiler_noise_analyst_subagent())
    return subagents


def variant_system_prompt(variant: str) -> str:
    base = load_prompt("supervisor.md")
    if variant == "single_agent":
        return (
            base + "\n\nAblation condition: single_agent. Do not delegate to specialist "
            "subagents. Make the final same-function judgment directly using the "
            "input code, deterministic tools if useful, and the FuncSim skill."
        )
    if variant == "wo_diffprobe":
        return (
            base + "\n\nAblation condition: wo_diffprobe. The difference_analyst subagent "
            "is intentionally unavailable. Do not ask for it. Make the final decision "
            "using semantic matching evidence, decompiler-noise evidence, deterministic "
            "tools, and the FuncSim skill."
        )
    if variant == "wo_noiselens":
        return (
            base + "\n\nAblation condition: wo_noiselens. The decompiler_noise_analyst "
            "subagent is intentionally unavailable. Do not ask for it. Make the final "
            "decision using semantic matching evidence, difference evidence, "
            "deterministic tools, and the FuncSim skill."
        )
    return base


def dedupe_preserve_order(values: list[int]) -> list[int]:
    seen: set[int] = set()
    result: list[int] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def print_ok(*, row_index: int, result: dict[str, Any]) -> None:
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
