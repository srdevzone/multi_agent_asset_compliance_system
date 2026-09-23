"""
Image agent — analyse each audit photo using LLM vision.

For each S3 key in state["s3_image_keys"], this node:
  1. Downloads the image as base64 from S3
  2. Passes it to the configured Claude model with a structured analysis prompt
  3. Parses the JSON response into an ImageAnalysis TypedDict

The prompt enforces a strict JSON response format so downstream agents
can rely on the structure without further LLM calls.

Non-fatal errors per image are caught and accumulated in state["errors"]
so that one bad image does not abort the entire audit.

Populates: state["image_analyses"]
"""

import asyncio
from typing import Any, cast

import structlog

from app.agents.state import AuditState, ImageAnalysis
from app.config import get_settings
from app.dependencies import get_image_agent_llm, get_s3_client
from app.schemas.image import ImageAnalysis as ImageAnalysisSchema
from app.services import s3_service
from app.utils.llm import call_structured_llm
from app.utils.retry import llm_retry

logger = structlog.get_logger(__name__)

_IMAGE_ANALYSIS_PROMPT = """Analyse this audit photograph of a physical asset for compliance purposes.

Be precise and technical. Document every visible defect, label, and condition indicator."""


@llm_retry
async def _process_single_image(
    s3_key: str, s3_client: Any, settings: Any, llm: Any
) -> ImageAnalysis | Exception:
    """Helper to process a single image, returning the analysis or catching the exception."""
    try:
        messages = [
            await s3_service.build_image_message(
                s3_client, settings.s3_bucket_name, s3_key, _IMAGE_ANALYSIS_PROMPT
            )
        ]

        parsed_obj = await call_structured_llm(llm, ImageAnalysisSchema, messages, "llm_image")
        parsed_obj.s3_key = s3_key

        analysis: ImageAnalysis = cast(ImageAnalysis, parsed_obj.model_dump())
        logger.debug(
            "image_analysed",
            s3_key=s3_key,
            condition=analysis["condition"],
            findings_count=len(analysis["findings"]),
        )
        return analysis

    except Exception as exc:
        logger.error("image_agent_error", s3_key=s3_key, error=type(exc).__name__)
        return exc


async def image_agent_node(state: AuditState) -> dict[str, Any]:
    """
    Analyse each audit image using Claude vision.

    Downloads images from S3 as base64 and sends them to the configured LLM with a
    structured analysis prompt concurrently. Parses the JSON response into ImageAnalysis
    TypedDicts. Per-image errors are caught and accumulated.

    Returns:
        dict with keys: image_analyses, errors
    """
    settings = get_settings()
    llm = get_image_agent_llm()
    s3_client = get_s3_client()

    analyses: list[ImageAnalysis] = []
    new_errors: list[str] = []

    s3_image_keys = state.get("s3_image_keys", [])
    if not s3_image_keys:
        return {"image_analyses": [], "errors": []}

    # Execute all image processing concurrently
    tasks = [_process_single_image(s3_key, s3_client, settings, llm) for s3_key in s3_image_keys]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    for s3_key, result in zip(s3_image_keys, results, strict=False):
        if isinstance(result, BaseException):
            # The exception is already logged inside _process_single_image
            new_errors.append(f"image_agent: {s3_key}: {result}")
        else:
            analyses.append(cast(ImageAnalysis, result))

    logger.info(
        "image_agent_complete",
        images_analysed=len(analyses),
        errors_count=len(new_errors),
    )
    return {"image_analyses": analyses, "errors": new_errors}
