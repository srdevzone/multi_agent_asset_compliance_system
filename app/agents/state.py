"""
AuditState — shared mutable context flowing through every LangGraph node.

Using TypedDict (not dataclass or Pydantic model) because LangGraph
requires plain dict-compatible types for its state merging mechanism.

All fields use total=False so agents can populate them progressively.
Each node receives the full current state and returns only the fields
it populates — LangGraph merges these partial dicts automatically.

Field groups:
  - Input: populated from AuditRequest before the graph starts
  - Per-agent outputs: populated as the graph progresses
  - Error accumulator: non-fatal errors are appended rather than raised
    so the graph always completes and returns a partial verdict
"""

import operator
from typing import Annotated, Any, TypedDict, cast

from app.schemas.audit import AssetSpec
from app.utils.sanitization import escape_dict


class ImageAnalysis(TypedDict):
    """Structured result of LLM vision analysis for one audit photo.

    Mirrors ``app.schemas.image.ImageAnalysis`` but remains a TypedDict so it
    can be stored directly in the LangGraph state dictionary.
    """

    s3_key: str
    findings: list[str]  # Specific observations about defects or non-compliance
    labels: list[str]  # Visible text labels, serial numbers, warning stickers
    condition: str  # "good" | "fair" | "poor" | "critical"
    raw_description: str  # Full paragraph describing everything visible


class RetrievedChunk(TypedDict):
    """One semantically-retrieved document chunk from Pinecone."""

    doc_id: str
    doc_type: str
    filename: str
    page: int | None
    text: str
    score: float
    parent_text: str | None  # Parent context for PDR mode


class AuditState(TypedDict, total=False):
    """
    Shared state dict for the LangGraph audit pipeline.

    All fields are optional at definition time (total=False).
    The input fields are populated before the graph starts.
    Agent nodes populate their respective output fields.
    """

    # ── Input — populated from AuditRequest before graph starts ──────────────
    asset_id: str
    run_id: str
    asset_spec: AssetSpec
    s3_image_keys: list[str]
    auditor_remarks: str | None
    previous_verdicts: list[dict[str, Any]] | None

    # ── document_agent output ─────────────────────────────────────────────────
    retrieved_chunks: list[RetrievedChunk]
    documents_consulted: list[str]  # Unique doc_ids from retrieved chunks

    # ── image_agent output ────────────────────────────────────────────────────
    image_analyses: list[ImageAnalysis]

    # ── rule_agent output ─────────────────────────────────────────────────────
    triggered_rules: list[dict[str, Any]]

    # ── evidence_agent output ─────────────────────────────────────────────────
    evidence_bundle: list[dict[str, Any]]
    evidence_truncated: bool  # True if evidence was truncated due to cap
    evidence_original_count: int  # Original count before truncation

    # ── verdict_agent output ──────────────────────────────────────────────────
    verdict: dict[str, Any] | None

    # ── Error accumulator — non-fatal errors from any agent ──────────────────
    errors: Annotated[list[str], operator.add]


def get_asset_spec_dict(state: Any) -> dict[str, Any]:
    """Helper to safely extract a dictionary representation of asset_spec from state.

    Handles cases where asset_spec is a dictionary or a Pydantic model.
    Applies HTML escaping to all string values to prevent prompt injection.
    """
    if not state:
        return {}
    if isinstance(state, dict):
        spec = state.get("asset_spec")
    else:
        spec = getattr(state, "asset_spec", None)

    if not spec:
        return {}
    if isinstance(spec, dict):
        return escape_dict(spec)
    if hasattr(spec, "model_dump"):
        return escape_dict(cast(dict[str, Any], spec.model_dump()))
    return {}
