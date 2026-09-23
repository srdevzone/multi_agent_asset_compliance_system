"""
Document loading and chunking service.

Supports PDF documents and image-type documents.

For PDFs:
  - Text is extracted page-by-page using pypdf
  - Each page's text is split into overlapping character-level chunks
  - Each chunk carries full metadata: asset_id, doc_id, doc_type, filename,
    chunk_index, page number, and the source text (stored for retrieval display)

For image documents (doc_type == "installation_image"):
  - A single vector is stored whose text is the LLM-generated description
  - The description is produced upstream by the image agent / ingest handler
  - This allows image documents to participate in semantic retrieval

Chunk metadata preserves all fields needed for source attribution in
evidence citations and chat responses.
"""

import hashlib
import io
from typing import Any

import structlog
from pypdf import PdfReader

from app.config import get_settings
from app.schemas.ingest import S3Document
from app.utils.time import utc_now_iso

logger = structlog.get_logger(__name__)


def _chunk_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    """
    Split text into overlapping chunks by character count.

    Overlap allows adjacent chunks to share context, reducing the chance
    that a relevant clause is split across chunk boundaries.
    """
    if chunk_size <= 0:
        raise ValueError(f"chunk_size must be positive, got {chunk_size}")
    if overlap < 0:
        raise ValueError(f"overlap must be non-negative, got {overlap}")
    if overlap >= chunk_size:
        raise ValueError(
            f"overlap ({overlap}) must be less than chunk_size ({chunk_size}) to prevent infinite loop"
        )

    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        start += chunk_size - overlap
    return [c.strip() for c in chunks if c.strip()]


def _chunk_text_parent_child(
    text: str,
    parent_size: int,
    child_size: int,
    child_overlap: int,
) -> list[dict[str, Any]]:
    """
    Split text into parent documents and child chunks for Parent-Document Retrieval.

    Parents are large context windows (e.g., 2048 chars) that provide broad context.
    Children are smaller retrieval units (e.g., 256 chars) that are embedded and searched.

    Each child chunk carries a reference to its parent's text for context expansion
    during retrieval.

    Returns:
        List of dicts with keys: 'parent_text', 'child_text', 'parent_index', 'child_index'
    """
    _validate_chunk_params(parent_size, child_size, child_overlap)

    results: list[dict[str, Any]] = []
    parent_chunks = _chunk_text(text, parent_size, 0)

    for parent_index, parent_text in enumerate(parent_chunks):
        if not parent_text:
            continue
        child_chunks = _chunk_text(parent_text, child_size, child_overlap)
        for child_index, child_text in enumerate(child_chunks):
            results.append(
                {
                    "parent_text": parent_text,
                    "child_text": child_text,
                    "parent_index": parent_index,
                    "child_index": child_index,
                }
            )

    return results


def _build_chunk_dict(
    doc_id: str,
    content_hash: str,
    page_num: int,
    chunk_idx: int,
    text: str,
    asset_id: str,
    doc_type: str,
    filename: str,
    parent_text: str | None = None,
    parent_index: int | None = None,
) -> dict[str, Any]:
    """
    Build a chunk dictionary with metadata for Pinecone upsert.

    Constructs the chunk_id and metadata dict with consistent structure
    for both PDR and legacy chunking modes.
    """
    metadata: dict[str, Any] = {
        "asset_id": asset_id,
        "doc_id": doc_id,
        "doc_type": doc_type,
        "filename": filename,
        "chunk_index": chunk_idx,
        "page": page_num,
        "embedded_at": utc_now_iso(),
        "text": text,
    }
    if parent_text is not None:
        metadata["parent_text"] = parent_text
        metadata["parent_index"] = parent_index
        metadata["is_child_chunk"] = True

    return {
        "chunk_id": f"{doc_id}_{content_hash}_p{page_num}_c{chunk_idx}",
        "text": text,
        "metadata": metadata,
    }


def _validate_chunk_params(parent_size: int, child_size: int, child_overlap: int) -> None:
    """Validate parent-child chunking parameters."""
    if parent_size <= 0:
        raise ValueError(f"parent_size must be positive, got {parent_size}")
    if child_size <= 0:
        raise ValueError(f"child_size must be positive, got {child_size}")
    if child_overlap < 0:
        raise ValueError(f"child_overlap must be non-negative, got {child_overlap}")
    if child_overlap >= child_size:
        raise ValueError(
            f"child_overlap ({child_overlap}) must be less than child_size ({child_size})"
        )
    if child_size > parent_size:
        raise ValueError(
            f"child_size ({child_size}) must be <= parent_size ({parent_size})"
        )


def load_pdf(
    raw_bytes: bytes,
    document: S3Document,
    asset_id: str,
) -> list[dict[str, Any]]:
    """
    Parse a PDF into text chunks ready for embedding and Pinecone upsert.

    Each returned dict has:
      - chunk_id: unique string ID for the vector
      - text: the chunk content (also stored in metadata for retrieval display)
      - metadata: all fields needed for source attribution

    When PDR is enabled, uses parent-child chunking where:
      - Parent documents are large context windows (pdr_parent_chunk_size)
      - Child chunks are smaller retrieval units (pdr_child_chunk_size)
      - Each child carries its parent's text for context expansion

    Empty pages are skipped silently.
    """
    settings = get_settings()
    try:
        reader = PdfReader(io.BytesIO(raw_bytes))
        pages_to_process = reader.pages
    except Exception as exc:
        logger.warning("pdf_parse_error", doc_id=document.doc_id, error=type(exc).__name__)
        return []
    chunks: list[dict[str, Any]] = []
    chunk_global_idx = 0
    content_hash = hashlib.sha256(raw_bytes).hexdigest()[:8]

    for page_num, page in enumerate(pages_to_process, start=1):
        page_text = page.extract_text() or ""
        if not page_text.strip():
            continue

        if settings.pdr_enabled:
            parent_child_chunks = _chunk_text_parent_child(
                page_text,
                parent_size=settings.pdr_parent_chunk_size,
                child_size=settings.pdr_child_chunk_size,
                child_overlap=settings.pdr_child_overlap,
            )
            for pc in parent_child_chunks:
                chunks.append(
                    _build_chunk_dict(
                        doc_id=document.doc_id,
                        content_hash=content_hash,
                        page_num=page_num,
                        chunk_idx=chunk_global_idx,
                        text=pc["child_text"],
                        asset_id=asset_id,
                        doc_type=document.doc_type,
                        filename=document.filename,
                        parent_text=pc["parent_text"],
                        parent_index=pc["parent_index"],
                    )
                )
                chunk_global_idx += 1
        else:
            # Legacy mode: flat chunking without parent context
            for chunk_text in _chunk_text(page_text, settings.chunk_size, settings.chunk_overlap):
                chunks.append(
                    _build_chunk_dict(
                        doc_id=document.doc_id,
                        content_hash=content_hash,
                        page_num=page_num,
                        chunk_idx=chunk_global_idx,
                        text=chunk_text,
                        asset_id=asset_id,
                        doc_type=document.doc_type,
                        filename=document.filename,
                    )
                )
                chunk_global_idx += 1

    logger.info(
        "pdf_loaded",
        doc_id=document.doc_id,
        filename=document.filename,
        pages=len(reader.pages),
        chunks=len(chunks),
        pdr_enabled=settings.pdr_enabled,
    )
    return chunks


def load_image_document(
    document: S3Document,
    asset_id: str,
    description: str,
) -> list[dict[str, Any]]:
    """
    Create a single vector record for an image-type document.

    The description is an LLM-generated text summary of the image,
    produced upstream by the image agent or ingest handler.
    Storing it as a vector allows the image to participate in semantic
    retrieval queries alongside PDF documents.
    """
    content_hash = hashlib.sha256(description.encode("utf-8")).hexdigest()[:8]
    chunk_id = f"{document.doc_id}_{content_hash}_img_0"
    return [
        {
            "chunk_id": chunk_id,
            "text": description,
            "metadata": {
                "asset_id": asset_id,
                "doc_id": document.doc_id,
                "doc_type": document.doc_type,
                "filename": document.filename,
                "chunk_index": 0,
                "page": None,
                "embedded_at": utc_now_iso(),
                "text": description,
            },
        }
    ]
