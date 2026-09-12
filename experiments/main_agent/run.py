"""Run the main FuncSim-Agent experiment."""

from pathlib import Path

from enterprise_agent.benchmarks.co2full.batch import main as run_batch


RUN_DIR = Path(__file__).resolve().parent / "runs" / "paper_initial"


def main(argv: list[str] | None = None) -> int:
    return run_batch(
        argv,
        default_trace_dir=RUN_DIR / "trace",
        default_report_dir=RUN_DIR / "report",
    )


if __name__ == "__main__":
    raise SystemExit(main())
