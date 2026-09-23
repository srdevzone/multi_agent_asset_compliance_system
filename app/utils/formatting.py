"""Shared formatting utilities for constructing LLM prompts from retrieved data."""

from collections.abc import Mapping
from typing import Any


def format_chunks_for_prompt(
    chunks: list[Any], *, separator: str = "\n\n"
) -> str:
    """
    Format retrieved document chunks as a structured text block for LLM prompts.

    When parent_text is available (from Parent-Document Retrieval), includes
    the parent context for broader document understanding.
    """
    if not chunks:
        return "No documents retrieved."

    formatted_parts = []
    for c in chunks:
        metadata = c.get("metadata", c)
        if not isinstance(metadata, Mapping):
            continue
        header = (
            f"[{metadata.get('filename', 'unknown')} | "
            f"page {metadata.get('page', 'N/A')} | {metadata.get('doc_type', '')}]"
        )
        child_text = str(metadata.get("text", ""))

        # Include parent context if available (PDR mode)
        parent_text = metadata.get("parent_text")
        if parent_text and parent_text != child_text:
            formatted_parts.append(
                f"{header}\n{child_text}\n\n[Parent Context]\n{parent_text}"
            )
        else:
            formatted_parts.append(f"{header}\n{child_text}")

    return separator.join(formatted_parts) or "No documents retrieved."
