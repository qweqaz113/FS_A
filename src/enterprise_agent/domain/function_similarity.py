from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field


class FunctionCompareInputError(ValueError):
    """Raised when a function comparison request cannot be parsed."""


@dataclass(frozen=True)
class FunctionCompareInput:
    raw_message: str
    code_a: str
    code_b: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class FunctionCompareVerdict:
    same_function: bool | None = None
    confidence: float | None = None
    summary: str = ""
    matching_evidence: list[str] = field(default_factory=list)
    difference_evidence: list[str] = field(default_factory=list)
    noise_assessment: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


_MARKER_RE = re.compile(r"(?im)^\s*(codea|codeb)\s*:\s*")


def parse_function_compare_input(message: str) -> FunctionCompareInput:
    """Parse a message containing top-level codea:/codeb: blocks."""
    matches = list(_MARKER_RE.finditer(message))
    if len(matches) < 2:
        raise FunctionCompareInputError("Input must contain both 'codea:' and 'codeb:' blocks.")

    blocks: dict[str, str] = {}
    for index, match in enumerate(matches):
        marker = match.group(1).lower()
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(message)
        blocks[marker] = message[start:end].strip()

    code_a = blocks.get("codea", "")
    code_b = blocks.get("codeb", "")
    if not code_a:
        raise FunctionCompareInputError("'codea:' block is empty.")
    if not code_b:
        raise FunctionCompareInputError("'codeb:' block is empty.")

    return FunctionCompareInput(
        raw_message=message,
        code_a=code_a,
        code_b=code_b,
    )
