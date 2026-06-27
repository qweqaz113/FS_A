from __future__ import annotations

from pydantic import BaseModel, Field


class FunctionSimilarityVerdict(BaseModel):
    same_function: bool = Field(
        description="Whether the two pseudocode blocks are the same function."
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description=(
            "Confidence in the final same_function verdict, not the probability that the "
            "functions are the same. Use a high value when confidently deciding either "
            "same_function=true or same_function=false. If the text says there is only "
            "0.10 probability/confidence that the functions are the same and the final "
            "verdict is different, report confidence as 0.90."
        ),
    )
    summary: str = Field(description="Short explanation of the final verdict.")
    matching_evidence: list[str] = Field(
        default_factory=list,
        description="Evidence supporting that the functions are the same.",
    )
    difference_evidence: list[str] = Field(
        default_factory=list,
        description="Evidence supporting that the functions differ.",
    )
    noise_assessment: list[str] = Field(
        default_factory=list,
        description="Decompiler or compiler artifact differences that should be discounted.",
    )
