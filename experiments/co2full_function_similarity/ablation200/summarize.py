from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from experiments.co2full_function_similarity.ablation200.common import (
    ABLATION_DIR,
    INITIAL_PREDICTIONS,
    REFINED_PREDICTIONS,
    calculate_metrics,
    load_predictions,
    load_report_predictions,
    load_subset,
    write_csv_rows,
    write_json,
)


DEFAULT_VARIANTS = [
    "single_agent",
    "initial_wo_refined_skill",
    "wo_diffprobe",
    "wo_noiselens",
    "full_refined",
]

METRIC_FIELDS = [
    "variant",
    "selected",
    "valid",
    "precision",
    "recall",
    "f2",
    "nv",
    "tp",
    "fp",
    "tn",
    "fn",
    "errors",
    "accuracy",
    "fpr",
]

BUCKET_FIELDS = [
    "variant",
    "bucket",
    "selected",
    "valid",
    "precision",
    "recall",
    "f2",
    "nv",
    "tp",
    "fp",
    "tn",
    "fn",
    "errors",
    "accuracy",
    "fpr",
]


def main() -> int:
    args = parse_args()
    subset = load_subset(Path(args.subset_csv))
    predictions_by_variant = load_variant_predictions(Path(args.output_root))

    metric_rows = []
    bucket_rows = []
    for variant in args.variants:
        predictions = predictions_by_variant[variant]
        rows = materialize_subset_predictions(subset, predictions)
        metrics = calculate_metrics(rows)
        metric_rows.append({"variant": variant, **metrics})

        for bucket in sorted(all_buckets(subset)):
            bucket_subset = [row for row in rows if bucket in row["buckets"].split(";")]
            bucket_metrics = calculate_metrics(bucket_subset)
            bucket_rows.append({"variant": variant, "bucket": bucket, **bucket_metrics})

    output_root = Path(args.output_root)
    write_csv_rows(output_root / "metrics.csv", metric_rows, METRIC_FIELDS)
    write_csv_rows(output_root / "bucket_breakdown.csv", bucket_rows, BUCKET_FIELDS)
    write_json(output_root / "metrics.json", metric_rows)
    write_markdown(output_root / "metrics.md", metric_rows, bucket_rows)

    print(f"Wrote metrics to: {output_root}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Summarize the 200-pair ablation results.")
    parser.add_argument("--subset-csv", default=ABLATION_DIR / "subset.csv")
    parser.add_argument("--output-root", default=ABLATION_DIR)
    parser.add_argument("--variants", nargs="+", default=DEFAULT_VARIANTS)
    return parser.parse_args()


def load_variant_predictions(output_root: Path) -> dict[str, dict[int, dict[str, Any]]]:
    return {
        "initial_wo_refined_skill": load_predictions(INITIAL_PREDICTIONS),
        "full_refined": load_predictions(REFINED_PREDICTIONS),
        "single_agent": load_report_predictions(output_root / "single_agent" / "report"),
        "wo_diffprobe": load_report_predictions(output_root / "wo_diffprobe" / "report"),
        "wo_noiselens": load_report_predictions(output_root / "wo_noiselens" / "report"),
        "full_refined_rerun": load_report_predictions(
            output_root / "full_refined_rerun" / "report"
        ),
    }


def materialize_subset_predictions(
    subset: list[dict[str, Any]],
    predictions: dict[int, dict[str, Any]],
) -> list[dict[str, Any]]:
    rows = []
    for subset_row in subset:
        row_index = subset_row["row_index"]
        prediction = predictions.get(row_index, {})
        pred_label = prediction.get("pred_label")
        label = subset_row["label"]
        rows.append(
            {
                "row_index": row_index,
                "label": label,
                "pred_label": pred_label,
                "correct": pred_label == label if pred_label in (0, 1) else None,
                "buckets": subset_row["buckets"],
            }
        )
    return rows


def all_buckets(subset: list[dict[str, Any]]) -> set[str]:
    buckets: set[str] = set()
    for row in subset:
        buckets.update(bucket for bucket in row["buckets"].split(";") if bucket)
    return buckets


def write_markdown(
    path: Path,
    metric_rows: list[dict[str, Any]],
    bucket_rows: list[dict[str, Any]],
) -> None:
    lines = [
        "# 200-Pair Targeted Ablation",
        "",
        "This diagnostic subset is enriched with previous errors and low-confidence correct cases.",
        "It is intended to stress component behavior, not to replace full-benchmark metrics.",
        "",
        "## Main Metrics",
        "",
        "| Variant | P | R | F2 | Nv | TP | FP | TN | FN | Errors | Acc | FPR |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in metric_rows:
        lines.append(
            f"| {row['variant']} | {row['precision']} | {row['recall']} | {row['f2']} | "
            f"{row['nv']} | {row['tp']} | {row['fp']} | {row['tn']} | {row['fn']} | "
            f"{row['errors']} | {row['accuracy']} | {row['fpr']} |"
        )

    lines.extend(
        [
            "",
            "## Bucket Error Breakdown",
            "",
            "| Variant | Bucket | Selected | Errors | FP | FN | F2 |",
            "|---|---|---:|---:|---:|---:|---:|",
        ]
    )
    for row in bucket_rows:
        lines.append(
            f"| {row['variant']} | {row['bucket']} | {row['selected']} | "
            f"{row['errors']} | {row['fp']} | {row['fn']} | {row['f2']} |"
        )
    path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
