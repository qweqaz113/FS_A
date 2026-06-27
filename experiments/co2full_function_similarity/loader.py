from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from enterprise_agent.domain.function_similarity import FunctionCompareInput
from experiments.co2full_function_similarity.paths import (
    DEFAULT_DB_ROOT,
    DEFAULT_PAIR_CSV,
    build_co2full_pair_key,
)


LEGACY_PAIR_CSV = (
    DEFAULT_DB_ROOT / "Binkit-1.0-dataset" / "pairs" / "experiments" / "xm-full_top5-250515.csv"
)
TOP_K_CODE_DIR = "Binkit-1.0-normal-strip-top_k_code"


class Co2FullLoadError(ValueError):
    """Raised when Co2FuLL pseudocode cannot be loaded."""


def load_co2full_pair_code(
    *,
    bin_name_1: str,
    fva_1: str,
    bin_name_2: str,
    fva_2: str,
    db_root: str | Path | None = None,
    source_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Load two pseudocode blocks from Co2FuLL top-k code JSON files."""
    root = _resolve_db_root(db_root)
    code_a = _load_pseudocode(root, bin_name_1, fva_1)
    code_b = _load_pseudocode(root, bin_name_2, fva_2)
    pair_key = build_co2full_pair_key(
        bin_name_1=bin_name_1,
        fva_1=fva_1,
        bin_name_2=bin_name_2,
        fva_2=fva_2,
    )
    metadata = {
        "type": "co2full_pair",
        "db_root": root.as_posix(),
        "bin_name_1": bin_name_1,
        "fva_1": fva_1,
        "bin_name_2": bin_name_2,
        "fva_2": fva_2,
        "pair_key": pair_key,
    }
    if source_metadata:
        metadata.update(source_metadata)
        metadata["pair_key"] = pair_key

    return {
        "compare_input": FunctionCompareInput(
            raw_message=f"codea:\n{code_a}\n\ncodeb:\n{code_b}",
            code_a=code_a,
            code_b=code_b,
        ),
        "source_metadata": metadata,
    }


def load_co2full_pair_by_row(
    *,
    row_index: int,
    csv_path: str | Path | None = None,
    db_root: str | Path | None = None,
) -> dict[str, Any]:
    """Load a Co2FuLL pair by zero-based row index from a pair CSV."""
    path = _resolve_csv_path(csv_path)
    row = _read_csv_row(path, row_index)
    required = ("bin_name_1", "fva_1", "bin_name_2", "fva_2")
    missing = [key for key in required if not row.get(key)]
    if missing:
        raise Co2FullLoadError(f"CSV row {row_index} is missing required columns: {missing}")

    return load_co2full_pair_code(
        bin_name_1=row["bin_name_1"],
        fva_1=row["fva_1"],
        bin_name_2=row["bin_name_2"],
        fva_2=row["fva_2"],
        db_root=db_root,
        source_metadata={
            "type": "co2full_row",
            "csv_path": path.as_posix(),
            "row_index": row_index,
            "label": _parse_label(row.get("label")),
            "func_name_1": row.get("func_name_1"),
            "func_name_2": row.get("func_name_2"),
            "db_type": row.get("db_type"),
            "csv_key_pair": row.get("key_pair"),
        },
    )


def build_code_json_path(db_root: str | Path, bin_name: str) -> Path:
    project = infer_project_name(bin_name)
    return Path(db_root) / TOP_K_CODE_DIR / project / f"{bin_name}.json"


def infer_project_name(bin_name: str) -> str:
    if "-" not in bin_name:
        raise Co2FullLoadError(f"Cannot infer project name from binary name: {bin_name}")
    return bin_name.split("-", 1)[0]


def _load_pseudocode(db_root: Path, bin_name: str, fva: str) -> str:
    json_path = build_code_json_path(db_root, bin_name)
    if not json_path.exists():
        raise Co2FullLoadError(f"Top-k code JSON not found: {json_path}")

    with json_path.open("r", encoding="utf-8") as file:
        data = json.load(file)

    for key in (fva, fva.lower(), fva.upper()):
        code_info = data.get(key)
        if code_info is not None:
            pseudo_code = code_info.get("pseudo_code", "")
            if not pseudo_code:
                raise Co2FullLoadError(f"Pseudocode is empty for {bin_name}@{fva}")
            return pseudo_code

    raise Co2FullLoadError(f"Function address {fva} not found in {json_path}")


def _read_csv_row(csv_path: Path, row_index: int) -> dict[str, str]:
    if row_index < 0:
        raise Co2FullLoadError("row_index must be non-negative.")
    if not csv_path.exists():
        raise Co2FullLoadError(f"Pair CSV not found: {csv_path}")

    with csv_path.open("r", encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file)
        for index, row in enumerate(reader):
            if index == row_index:
                return dict(row)

    raise Co2FullLoadError(f"CSV row index out of range: {row_index}")


def _resolve_db_root(db_root: str | Path | None) -> Path:
    raw_root = Path(db_root) if db_root is not None else DEFAULT_DB_ROOT
    return raw_root.resolve()


def _resolve_csv_path(csv_path: str | Path | None) -> Path:
    if csv_path is not None:
        return Path(csv_path).resolve()
    if DEFAULT_PAIR_CSV.exists():
        return DEFAULT_PAIR_CSV.resolve()
    return LEGACY_PAIR_CSV.resolve()


def _parse_label(value: str | None) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except ValueError:
        return None
