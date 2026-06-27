from __future__ import annotations

import argparse
from collections import Counter
from typing import Any

from experiments.co2full_function_similarity.ablation200.common import (
    INITIAL_PREDICTIONS,
    REFINED_PREDICTIONS,
    SUBSET_CSV,
    SUBSET_JSON,
    load_predictions,
    write_csv_rows,
    write_json,
)


TARGET_SIZE = 200
TARGET_HARD_NEGATIVES = 75
TARGET_TRUE_POSITIVES = 50

FIELDNAMES = [
    "selection_rank",
    "row_index",
    "label",
    "buckets",
    "initial_pred",
    "refined_pred",
    "initial_correct",
    "refined_correct",
    "initial_confidence",
    "refined_confidence",
    "query_key",
    "pair_key",
    "initial_report_path",
    "refined_report_path",
]


def main() -> int:
    args = parse_args()
    initial = load_predictions(args.initial_predictions)
    refined = load_predictions(args.refined_predictions)

    selected: dict[int, dict[str, Any]] = {}
    add_bucket(selected, initial_fp(initial), initial, refined, "initial_fp")
    add_bucket(selected, initial_fn(initial), initial, refined, "initial_fn")
    add_bucket(selected, refined_errors(refined), initial, refined, "refined_error")
    add_bucket(
        selected,
        hard_negative_non_errors(initial, refined),
        initial,
        refined,
        "hard_negative_non_error",
        limit=args.hard_negatives,
    )
    add_bucket(
        selected,
        true_positive_non_errors(initial, refined),
        initial,
        refined,
        "true_positive_non_error",
        limit=args.true_positives,
    )

    if len(selected) < args.target_size:
        add_bucket(
            selected,
            low_confidence_correct_fillers(initial, refined),
            initial,
            refined,
            "low_confidence_correct_filler",
            limit=args.target_size - len(selected),
        )

    rows = list(selected.values())[: args.target_size]
    for index, row in enumerate(rows, start=1):
        row["selection_rank"] = index
        row["buckets"] = ";".join(row["buckets"])

    write_csv_rows(args.output_csv, rows, FIELDNAMES)
    summary = build_summary(rows)
    write_json(args.output_json, summary)

    print(f"Wrote subset: {args.output_csv}")
    print(f"Wrote summary: {args.output_json}")
    print(f"Selected rows: {len(rows)}")
    print(f"Bucket counts: {summary['bucket_counts']}")
    print(f"Label counts: {summary['label_counts']}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build the 200-pair targeted stress subset for component ablation."
    )
    parser.add_argument("--initial-predictions", type=str, default=INITIAL_PREDICTIONS)
    parser.add_argument("--refined-predictions", type=str, default=REFINED_PREDICTIONS)
    parser.add_argument("--output-csv", type=str, default=SUBSET_CSV)
    parser.add_argument("--output-json", type=str, default=SUBSET_JSON)
    parser.add_argument("--target-size", type=int, default=TARGET_SIZE)
    parser.add_argument("--hard-negatives", type=int, default=TARGET_HARD_NEGATIVES)
    parser.add_argument("--true-positives", type=int, default=TARGET_TRUE_POSITIVES)
    return parser.parse_args()


def initial_fp(initial: dict[int, dict[str, Any]]) -> list[int]:
    return sorted(
        row_index
        for row_index, row in initial.items()
        if row["label"] == 0 and row["pred_label"] == 1
    )


def initial_fn(initial: dict[int, dict[str, Any]]) -> list[int]:
    return sorted(
        row_index
        for row_index, row in initial.items()
        if row["label"] == 1 and row["pred_label"] == 0
    )


def refined_errors(refined: dict[int, dict[str, Any]]) -> list[int]:
    return sorted(row_index for row_index, row in refined.items() if row["correct"] is False)


def hard_negative_non_errors(
    initial: dict[int, dict[str, Any]],
    refined: dict[int, dict[str, Any]],
) -> list[int]:
    candidates = []
    for row_index, row in initial.items():
        refined_row = refined.get(row_index)
        if not refined_row:
            continue
        if row["label"] != 0:
            continue
        if row["correct"] is True and refined_row["correct"] is True:
            candidates.append((hardness_score(row, refined_row), row_index))
    return [row_index for _, row_index in sorted(candidates)]


def true_positive_non_errors(
    initial: dict[int, dict[str, Any]],
    refined: dict[int, dict[str, Any]],
) -> list[int]:
    candidates = []
    for row_index, row in initial.items():
        refined_row = refined.get(row_index)
        if not refined_row:
            continue
        if row["label"] != 1:
            continue
        if row["correct"] is True and refined_row["correct"] is True:
            candidates.append((hardness_score(row, refined_row), row_index))
    return [row_index for _, row_index in sorted(candidates)]


def low_confidence_correct_fillers(
    initial: dict[int, dict[str, Any]],
    refined: dict[int, dict[str, Any]],
) -> list[int]:
    candidates = []
    for row_index, row in initial.items():
        refined_row = refined.get(row_index)
        if not refined_row:
            continue
        if row["correct"] is True and refined_row["correct"] is True:
            candidates.append((hardness_score(row, refined_row), row_index))
    return [row_index for _, row_index in sorted(candidates)]


def hardness_score(initial_row: dict[str, Any], refined_row: dict[str, Any]) -> tuple[float, int]:
    confidences = [
        value
        for value in (initial_row.get("confidence"), refined_row.get("confidence"))
        if isinstance(value, (int, float))
    ]
    confidence = min(confidences) if confidences else 1.0
    row_index = initial_row.get("row_index") or 0
    return (confidence, row_index)


def add_bucket(
    selected: dict[int, dict[str, Any]],
    row_indices: list[int],
    initial: dict[int, dict[str, Any]],
    refined: dict[int, dict[str, Any]],
    bucket: str,
    *,
    limit: int | None = None,
) -> None:
    added = 0
    for row_index in row_indices:
        initial_row = initial.get(row_index)
        refined_row = refined.get(row_index)
        if not initial_row or not refined_row:
            continue
        was_new = row_index not in selected
        if row_index not in selected:
            selected[row_index] = make_subset_row(initial_row, refined_row)
        if bucket not in selected[row_index]["buckets"]:
            selected[row_index]["buckets"].append(bucket)
        if was_new:
            added += 1
        if limit is not None and added >= limit:
            break


def make_subset_row(initial_row: dict[str, Any], refined_row: dict[str, Any]) -> dict[str, Any]:
    return {
        "selection_rank": "",
        "row_index": initial_row["row_index"],
        "label": initial_row["label"],
        "buckets": [],
        "initial_pred": initial_row["pred_label"],
        "refined_pred": refined_row["pred_label"],
        "initial_correct": initial_row["correct"],
        "refined_correct": refined_row["correct"],
        "initial_confidence": initial_row["confidence"],
        "refined_confidence": refined_row["confidence"],
        "query_key": initial_row["query_key"],
        "pair_key": initial_row["pair_key"],
        "initial_report_path": initial_row["report_path"],
        "refined_report_path": refined_row["report_path"],
    }


def build_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    bucket_counts: Counter[str] = Counter()
    for row in rows:
        for bucket in str(row["buckets"]).split(";"):
            if bucket:
                bucket_counts[bucket] += 1
    return {
        "selected": len(rows),
        "label_counts": dict(Counter(str(row["label"]) for row in rows)),
        "bucket_counts": dict(bucket_counts),
        "initial_errors_in_subset": sum(1 for row in rows if row["initial_correct"] is False),
        "refined_errors_in_subset": sum(1 for row in rows if row["refined_correct"] is False),
    }


if __name__ == "__main__":
    raise SystemExit(main())
