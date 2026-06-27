from __future__ import annotations


def main() -> None:
    print("FuncSim-Agent: multi-agent verification for binary function similarity")
    print("\nReproducibility commands:")
    print(
        "  uv run python -m "
        "experiments.co2full_function_similarity.workflows.run_batch --help"
    )
    print(
        "  uv run python -m "
        "experiments.co2full_function_similarity.evaluation.evaluate_reports --help"
    )
    print(
        "  uv run python -m "
        "experiments.co2full_function_similarity.workflows.run_batch_refinement --help"
    )
    print("\nSee README.md for dataset layout, sandbox setup, and the complete workflow.")


if __name__ == "__main__":
    main()
