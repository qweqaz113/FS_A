from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

def main(
    argv: list[str] | None = None,
    *,
    default_report_dir: str | Path | None = None,
    default_eval_dir: str | Path | None = None,
) -> int:
    args = _parse_args(
        argv,
        default_report_dir=Path(default_report_dir) if default_report_dir is not None else None,
        default_eval_dir=Path(default_eval_dir) if default_eval_dir is not None else None,
    )
    reports = load_reports(args.report_dir)
    predictions = build_predictions(reports)
    metrics = calculate_metrics(
        predictions,
        beta=args.beta,
        total_target_queries=args.total_target_queries,
    )

    eval_dir = args.eval_dir
    eval_dir.mkdir(parents=True, exist_ok=True)
    write_json(eval_dir / "metrics.json", metrics)
    write_predictions_csv(eval_dir / "predictions.csv", predictions)
    write_errors_csv(eval_dir / "errors.csv", predictions)
    write_metrics_md(
        eval_dir / "metrics.md",
        metrics,
        predictions,
        total_target_queries=args.total_target_queries,
    )

    print(f"Loaded reports: {len(reports)}")
    print(f"Valid predictions: {sum(1 for row in predictions if row['pred_label'] in (0, 1))}")
    print(f"Wrote eval files to: {eval_dir.resolve()}")
    return 0


def _parse_args(
    argv: list[str] | None,
    *,
    default_report_dir: Path | None,
    default_eval_dir: Path | None,
) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate FuncSim-Agent JSON reports.")
    parser.add_argument(
        "--report-dir",
        type=Path,
        default=default_report_dir,
        required=default_report_dir is None,
    )
    parser.add_argument(
        "--eval-dir",
        type=Path,
        default=default_eval_dir,
        required=default_eval_dir is None,
    )
    parser.add_argument("--beta", type=int, default=2)
    parser.add_argument(
        "--total-target-queries",
        type=int,
        default=500,
        help="Recall denominator used by the D1 benchmark.",
    )
    return parser.parse_args(argv)


def load_reports(report_dir: Path) -> list[dict[str, Any]]:
    reports = []
    if not report_dir.exists():
        raise FileNotFoundError(f"Report directory not found: {report_dir}")

    for path in sorted(report_dir.glob("*.json")):
        with path.open("r", encoding="utf-8") as file:
            report = json.load(file)
        report["_report_path"] = path.as_posix()
        reports.append(report)
    return reports


def build_predictions(reports: list[dict[str, Any]]) -> list[dict[str, Any]]:
    predictions = []
    for report in reports:
        source = report.get("source") or {}
        label = _parse_optional_int(source.get("label"))
        same_function = report.get("same_function")
        if same_function is True:
            pred_label = 1
        elif same_function is False:
            pred_label = 0
        else:
            pred_label = None

        row = {
            "row_index": _parse_optional_int(source.get("row_index")),
            "query_key": _query_key(source),
            "pair_key": report.get("pair_key") or source.get("pair_key"),
            "label": label,
            "pred_label": pred_label,
            "correct": pred_label == label if pred_label in (0, 1) and label in (0, 1) else None,
            "confidence": report.get("confidence"),
            "summary": report.get("summary", ""),
            "report_path": report.get("_report_path"),
        }
        predictions.append(row)

    return sorted(
        predictions,
        key=lambda row: (
            row["query_key"] or "",
            row["row_index"] if row["row_index"] is not None else 10**18,
            row["pair_key"] or "",
        ),
    )


def calculate_metrics(
    predictions: list[dict[str, Any]],
    *,
    beta: int,
    total_target_queries: int | None,
) -> dict[str, Any]:
    valid = [row for row in predictions if row["pred_label"] in (0, 1) and row["label"] in (0, 1)]

    tp = sum(1 for row in valid if row["pred_label"] == 1 and row["label"] == 1)
    fp = sum(1 for row in valid if row["pred_label"] == 1 and row["label"] != 1)
    fn = sum(1 for row in valid if row["pred_label"] != 1 and row["label"] == 1)
    tn = sum(1 for row in valid if row["pred_label"] != 1 and row["label"] != 1)
    total = tp + fp + tn + fn

    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall_denominator = total_target_queries if total_target_queries is not None else tp + fn
    recall = tp / recall_denominator if recall_denominator else 0.0
    fpr = fp / (fp + tn) if (fp + tn) else 0.0
    accuracy = (tp + tn) / total if total else 0.0
    beta_sq = beta**2
    f_beta = (
        (1 + beta_sq) * precision * recall / (beta_sq * precision + recall)
        if (beta_sq * precision + recall)
        else 0.0
    )
    supp_rate = len(valid) / len(predictions) if predictions else 0.0

    return {
        "nv": tp + fp,
        "selected": len(predictions),
        "valid": len(valid),
        "recall_denominator": recall_denominator,
        "tp": tp,
        "fp": fp,
        "tn": tn,
        "fn": fn,
        "precision": round(precision * 100, 1),
        "recall": round(recall * 100, 1),
        "f2": round(f_beta * 100, 1),
        "fpr": round(fpr * 100, 1),
        "accuracy": round(accuracy * 100, 1),
        "supp_rate": round(supp_rate * 100, 1),
    }


def write_predictions_csv(path: Path, predictions: list[dict[str, Any]]) -> None:
    fieldnames = [
        "row_index",
        "query_key",
        "pair_key",
        "label",
        "pred_label",
        "correct",
        "confidence",
        "summary",
        "report_path",
    ]
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(predictions)


def write_errors_csv(path: Path, predictions: list[dict[str, Any]]) -> None:
    errors = [row for row in predictions if row["correct"] is False]
    write_predictions_csv(path, errors)


def write_metrics_md(
    path: Path,
    metrics: dict[str, Any],
    predictions: list[dict[str, Any]],
    *,
    total_target_queries: int | None,
) -> None:
    lines = [
        "# Co2FuLL Function Similarity Evaluation",
        "",
        "This evaluation is computed only over the reports currently present in `REPORT_DIR`.",
        "When the full report set is available, rerun the same script for full metrics.",
        "",
        "## Metrics",
        "",
        "| P | R | F2 | Nv | TP | FP | TN | FN | Acc | FPR | Supp |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    lines.append(
        f"| {metrics['precision']} | {metrics['recall']} | {metrics['f2']} | "
        f"{metrics['nv']} | {metrics['tp']} | {metrics['fp']} | {metrics['tn']} | "
        f"{metrics['fn']} | {metrics['accuracy']} | {metrics['fpr']} | "
        f"{metrics['supp_rate']} |"
    )

    lines.extend(
        [
            "",
            "## Meaning",
            "",
            "- `P`: Precision. Among pairs predicted as same, the percentage that are truly same (`label=1`). Higher means fewer false positives.",
            "- `R`: Recall. Among target functions, the percentage correctly reported as same. The denominator is controlled by `--total-target-queries` and defaults to 500 for the paper's D1 evaluation.",
            "- `F2`: F-beta score with beta=2. It combines precision and recall but gives recall four times the weight of precision.",
            "- `Nv`: number of reported positives requiring verification, equal to `TP + FP`, matching the paper's definition.",
            "- `TP`: predicted same and label is same.",
            "- `FP`: predicted same but label is different.",
            "- `TN`: predicted different and label is different.",
            "- `FN`: predicted different but label is same.",
            "- `Acc`: overall accuracy over valid pairs.",
            "- `FPR`: false-positive rate, i.e. different pairs incorrectly predicted as same.",
            "- `Supp`: support rate, the percentage of selected reports that have valid labels and predictions.",
            "",
            "## Dataset Size",
            "",
            f"- Reports loaded: {len(predictions)}",
            f"- Valid predictions: {sum(1 for row in predictions if row['pred_label'] in (0, 1) and row['label'] in (0, 1))}",
            f"- Error rows: {sum(1 for row in predictions if row['correct'] is False)}",
            f"- TOTAL_TARGET_QUERIES: {total_target_queries if total_target_queries is not None else 'current selected positives'}",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def _query_key(source: dict[str, Any]) -> str | None:
    bin_name = source.get("bin_name_1")
    fva = source.get("fva_1")
    if not bin_name or not fva:
        return None
    return f"{bin_name}@{fva}"


def _parse_optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


if __name__ == "__main__":
    raise SystemExit(main())
