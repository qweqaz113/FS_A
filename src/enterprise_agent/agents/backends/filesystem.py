from pathlib import Path


def sandbox_path() -> Path:
    return Path("data/sandbox").resolve()
