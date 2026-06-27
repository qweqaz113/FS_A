from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any, Mapping


EXPERIMENT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = EXPERIMENT_DIR / "data"
DEFAULT_DB_ROOT = DATA_DIR / "dbs"
DEFAULT_PAIR_CSV = DEFAULT_DB_ROOT / "xm-full_top5-250515.csv"
TRACE_DIR = DATA_DIR / "trace"
REPORT_DIR = DATA_DIR / "report"
MAX_RESULT_FILENAME_LENGTH = 120

_UNSAFE_FILENAME_CHARS_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def build_co2full_pair_key(
    *,
    bin_name_1: str,
    fva_1: str,
    bin_name_2: str,
    fva_2: str,
) -> str:
    return f"{bin_name_1}@{fva_1}#{bin_name_2}@{fva_2}"


def pair_key_from_metadata(source_metadata: Mapping[str, Any] | None) -> str | None:
    if not source_metadata:
        return None

    direct_key = source_metadata.get("pair_key") or source_metadata.get("key_pair")
    if direct_key:
        return str(direct_key)

    required = ("bin_name_1", "fva_1", "bin_name_2", "fva_2")
    if not all(source_metadata.get(key) for key in required):
        return None

    return build_co2full_pair_key(
        bin_name_1=str(source_metadata["bin_name_1"]),
        fva_1=str(source_metadata["fva_1"]),
        bin_name_2=str(source_metadata["bin_name_2"]),
        fva_2=str(source_metadata["fva_2"]),
    )


def safe_result_filename(file_stem: str) -> str:
    safe_stem = _safe_result_stem(file_stem)
    return f"{safe_stem or 'comparison'}.json"


def compact_result_filename(file_stem: str) -> str:
    safe_stem = _safe_result_stem(file_stem) or "comparison"
    legacy_filename = f"{safe_stem}.json"
    if len(legacy_filename) <= MAX_RESULT_FILENAME_LENGTH:
        return legacy_filename

    digest = hashlib.sha1(file_stem.encode("utf-8")).hexdigest()[:12]
    suffix = f"-{digest}.json"
    max_prefix_len = MAX_RESULT_FILENAME_LENGTH - len(suffix)
    prefix = safe_stem[:max_prefix_len].rstrip(" ._-") or "comparison"
    return f"{prefix}{suffix}"


def trace_path_for(pair_key: str, trace_dir: str | Path = TRACE_DIR) -> Path:
    return result_path_for(pair_key, trace_dir)


def report_path_for(pair_key: str, report_dir: str | Path = REPORT_DIR) -> Path:
    return result_path_for(pair_key, report_dir)


def result_path_for(file_stem: str, result_dir: str | Path) -> Path:
    result_dir = Path(result_dir)
    legacy_path = result_dir / safe_result_filename(file_stem)
    if _path_exists(legacy_path):
        return legacy_path
    return result_dir / compact_result_filename(file_stem)


def _safe_result_stem(file_stem: str) -> str:
    return _UNSAFE_FILENAME_CHARS_RE.sub("_", file_stem).strip(" .")


def _path_exists(path: Path) -> bool:
    try:
        return path.exists()
    except OSError:
        return False
