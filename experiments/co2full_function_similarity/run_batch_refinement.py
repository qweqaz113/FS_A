"""Compatibility entry point for the refined full-benchmark run."""

from experiments.co2full_function_similarity.paths import DATA_DIR
from experiments.co2full_function_similarity.run_batch import main as run_batch


REFINEMENT_DIR = DATA_DIR / "refinement_full"


def main(argv: list[str] | None = None) -> int:
    """Run the shared batch driver with refinement-specific output directories."""
    return run_batch(
        argv,
        default_trace_dir=REFINEMENT_DIR / "trace",
        default_report_dir=REFINEMENT_DIR / "report",
    )


if __name__ == "__main__":
    raise SystemExit(main())
