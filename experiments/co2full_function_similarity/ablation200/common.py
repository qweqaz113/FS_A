from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from typing import Any, Iterable


EXPERIMENT_DIR = Path(__file__).resolve().parents[1]
ROOT_DIR = Path(__file__).resolve().parents[3]
SRC_DIR = ROOT_DIR / "src"
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


DATA_DIR = EXPERIMENT_DIR / "data"
ABLATION_DIR = DATA_DIR / "ablation200"
SUBSET_CSV = ABLATION_DIR / "subset.csv"
SUBSET_JSON = ABLATION_DIR / "subset_summary.json"

INITIAL_PREDICTIONS = DATA_DIR / "eval" / "predictions.csv"
REFINED_PREDICTIONS = DATA_DIR / "refine_eval" / "predictions.csv"
INITIAL_REPORT_DIR = DATA_DIR / "report"
REFINED_REPORT_DIR = DATA_DIR / "refinement_full" / "report"

CSV_PATH = DATA_DIR / "dbs" / "xm-full_top5-250515.csv"
DB_ROOT = DATA_DIR / "dbs"

BETA = 2


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as file:
        return list(csv.DictReader(file))


def write_csv_rows(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def load_predictions(path: Path) -> dict[int, dict[str, Any]]:
    rows: dict[int, dict[str, Any]] = {}
    for row in read_csv_rows(path):
        row_index = parse_optional_int(row.get("row_index"))
        if row_index is None:
            continue
        rows[row_index] = normalize_prediction_row(row)
    return rows


def normalize_prediction_row(row: dict[str, Any]) -> dict[str, Any]:
    label = parse_optional_int(row.get("label"))
    pred_label = parse_optional_int(row.get("pred_label"))
    return {
        "row_index": parse_optional_int(row.get("row_index")),
        "query_key": row.get("query_key") or "",
        "pair_key": row.get("pair_key") or "",
        "label": label,
        "pred_label": pred_label,
        "correct": parse_optional_bool(row.get("correct")),
        "confidence": parse_optional_float(row.get("confidence")),
        "summary": row.get("summary") or "",
        "report_path": row.get("report_path") or "",
    }


def load_subset(path: Path = SUBSET_CSV) -> list[dict[str, Any]]:
    rows = []
    for row in read_csv_rows(path):
        rows.append(
            {
                **row,
                "row_index": parse_optional_int(row.get("row_index")),
                "label": parse_optional_int(row.get("label")),
                "initial_pred": parse_optional_int(row.get("initial_pred")),
                "refined_pred": parse_optional_int(row.get("refined_pred")),
                "initial_correct": parse_optional_bool(row.get("initial_correct")),
                "refined_correct": parse_optional_bool(row.get("refined_correct")),
            }
        )
    return rows


def load_report_predictions(report_dir: Path) -> dict[int, dict[str, Any]]:
    predictions: dict[int, dict[str, Any]] = {}
    for path in sorted(report_dir.glob("*.json")):
        report = json.loads(path.read_text(encoding="utf-8"))
        source = report.get("source") or {}
        row_index = parse_optional_int(source.get("row_index"))
        label = parse_optional_int(source.get("label"))
        if row_index is None or label is None:
            continue
        same_function = report.get("same_function")
        if same_function is True:
            pred_label = 1
        elif same_function is False:
            pred_label = 0
        else:
            pred_label = None
        predictions[row_index] = {
            "row_index": row_index,
            "query_key": query_key(source),
            "pair_key": report.get("pair_key") or source.get("pair_key") or "",
            "label": label,
            "pred_label": pred_label,
            "correct": pred_label == label if pred_label in (0, 1) else None,
            "confidence": parse_optional_float(report.get("confidence")),
            "summary": report.get("summary") or "",
            "report_path": path.as_posix(),
        }
    return predictions


def calculate_metrics(rows: Iterable[dict[str, Any]], *, beta: int = BETA) -> dict[str, Any]:
    row_list = list(rows)
    valid = [
        row for row in row_list if row.get("pred_label") in (0, 1) and row.get("label") in (0, 1)
    ]
    tp = sum(1 for row in valid if row["pred_label"] == 1 and row["label"] == 1)
    fp = sum(1 for row in valid if row["pred_label"] == 1 and row["label"] == 0)
    tn = sum(1 for row in valid if row["pred_label"] == 0 and row["label"] == 0)
    fn = sum(1 for row in valid if row["pred_label"] == 0 and row["label"] == 1)
    total = tp + fp + tn + fn

    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    beta_sq = beta * beta
    f_beta = (
        (1 + beta_sq) * precision * recall / (beta_sq * precision + recall)
        if (beta_sq * precision + recall)
        else 0.0
    )
    accuracy = (tp + tn) / total if total else 0.0
    fpr = fp / (fp + tn) if (fp + tn) else 0.0

    return {
        "selected": len(row_list),
        "valid": len(valid),
        "nv": tp + fp,
        "tp": tp,
        "fp": fp,
        "tn": tn,
        "fn": fn,
        "errors": fp + fn,
        "precision": round(precision * 100, 1),
        "recall": round(recall * 100, 1),
        "f2": round(f_beta * 100, 1),
        "accuracy": round(accuracy * 100, 1),
        "fpr": round(fpr * 100, 1),
    }


def parse_optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def parse_optional_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_optional_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if value in (None, ""):
        return None
    text = str(value).strip().lower()
    if text == "true":
        return True
    if text == "false":
        return False
    return None


def query_key(source: dict[str, Any]) -> str:
    bin_name = source.get("bin_name_1")
    fva = source.get("fva_1")
    if not bin_name or not fva:
        return ""
    return f"{bin_name}@{fva}"
