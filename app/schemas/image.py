"""Pydantic schemas for image analysis results."""

from pydantic import BaseModel, Field


class ImageAnalysis(BaseModel):
    """Structured result of LLM vision analysis for one audit photo."""

    s3_key: str = Field(..., description="S3 object key of the analysed image")
    findings: list[str] = Field(
        default_factory=list,
        description="Specific observations about defects or non-compliance",
    )
    labels: list[str] = Field(
        default_factory=list,
        description="Visible text labels, serial numbers, warning stickers",
    )
    condition: str = Field(
        ..., description="Overall condition rating (e.g. good, fair, poor, critical)"
    )
    raw_description: str = Field(
        ..., description="Full paragraph describing everything visible in the image"
    )
