"""Evaluate the default Co2FuLL v4 baseline run."""

from pathlib import Path

from enterprise_agent.benchmarks.co2full.evaluation import main as evaluate_reports


RUN_DIR = Path(__file__).resolve().parent / "runs" / "deepseek_v4"


def main(argv: list[str] | None = None) -> int:
    return evaluate_reports(
        argv,
        default_report_dir=RUN_DIR / "report",
        default_eval_dir=RUN_DIR / "evaluation",
    )


if __name__ == "__main__":
    raise SystemExit(main())
