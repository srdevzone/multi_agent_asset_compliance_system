"""
S3 service — download documents and images for processing.

Provides:
  - Raw byte download for PDF processing
  - Base64 download for LLM vision calls (multimodal content blocks)
  - Presigned URL generation for secure temporary access
  - MIME type inference from filename extension
  - Multimodal image message construction for LLM vision calls

All download functions include tenacity retry logic for transient S3 errors.
"""

import base64
from typing import Any

import structlog
from langchain_core.messages import HumanMessage

from app.utils.async_helpers import run_in_thread
from app.utils.resilience import s3_call

logger = structlog.get_logger(__name__)


_MIME_MAP: dict[str, str] = {
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "gif": "image/gif",
    "webp": "image/webp",
    "pdf": "application/pdf",
}


@s3_call
def _download_bytes_sync(s3_client: Any, bucket: str, key: str) -> bytes:
    """Download an S3 object and return its raw bytes synchronously."""
    response = s3_client.get_object(Bucket=bucket, Key=key)
    data: bytes = response["Body"].read()
    logger.debug("s3_download_complete", bucket=bucket, key=key, size_bytes=len(data))
    return data


download_bytes = run_in_thread(_download_bytes_sync)


def _download_as_base64_sync(s3_client: Any, bucket: str, key: str) -> str:
    """Download an S3 image and return it as a base64-encoded string synchronously."""
    raw = _download_bytes_sync(s3_client, bucket, key)
    encoded = base64.standard_b64encode(raw).decode("utf-8")
    logger.debug("s3_base64_encoded", bucket=bucket, key=key)
    return encoded


download_as_base64 = run_in_thread(_download_as_base64_sync)


@s3_call
def _generate_presigned_url_sync(
    s3_client: Any,
    bucket: str,
    key: str,
    expiry_seconds: int = 3600,
) -> str:
    """Generate a presigned URL synchronously."""
    url: str = s3_client.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": key},
        ExpiresIn=expiry_seconds,
    )
    logger.debug("presigned_url_generated", bucket=bucket, key=key, expiry=expiry_seconds)
    return url


generate_presigned_url = run_in_thread(_generate_presigned_url_sync)


def infer_media_type(filename: str) -> str:
    """
    Infer the MIME type from a file extension.

    Used when constructing LLM vision content blocks that require an
    explicit media_type field. Falls back to 'application/octet-stream'
    for unrecognised extensions.
    """
    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    return _MIME_MAP.get(ext, "application/octet-stream")


async def build_image_message(
    s3_client: Any,
    bucket: str,
    s3_key: str,
    prompt_text: str,
) -> HumanMessage:
    """Download an S3 image, encode as base64, and construct a multimodal HumanMessage."""
    image_b64 = await download_as_base64(s3_client, bucket, s3_key)
    filename = s3_key.rsplit("/", 1)[-1]
    media_type = infer_media_type(filename)
    image_url = f"data:{media_type};base64,{image_b64}"
    return HumanMessage(
        content=[
            {"type": "text", "text": prompt_text},
            {"type": "image_url", "image_url": {"url": image_url}},
        ]
    )


@s3_call
def _delete_asset_documents_sync(s3_client: Any, bucket: str, asset_id: str) -> int:
    """Delete all S3 objects under an asset prefix synchronously."""
    prefix = f"{asset_id}/"
    paginator = s3_client.get_paginator("list_objects_v2")
    deleted_count = 0

    try:
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            if "Contents" in page:
                objects = [{"Key": obj["Key"]} for obj in page["Contents"]]
                if objects:
                    s3_client.delete_objects(
                        Bucket=bucket, Delete={"Objects": objects, "Quiet": True}
                    )
                    deleted_count += len(objects)
    except Exception as e:
        error_name = type(e).__name__
        if "NoSuchBucket" in error_name:
            logger.debug("s3_bucket_not_found_for_erasure", bucket=bucket)
            return 0
        raise

    logger.debug(
        "s3_asset_documents_deleted", bucket=bucket, asset_id=asset_id, count=deleted_count
    )
    return deleted_count


delete_asset_documents = run_in_thread(_delete_asset_documents_sync)
