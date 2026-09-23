"""
Evidence agent — consolidate all findings into a structured evidence bundle.

This node merges outputs from three sources into a unified list of evidence
dicts that the verdict agent will consume:
  1. Retrieved document chunks (source_type: "document")
  2. Image analysis findings (source_type: "image")
  3. Auditor remarks (source_type: "auditor_remark")

Each evidence item is normalised to a common structure regardless of source.
This normalisation makes it straightforward for the verdict agent to reason
across heterogeneous evidence types in a single LLM call.

Populates: state["evidence_bundle"]
"""

from typing import Any

import structlog

from app.agents.state import AuditState
from app.config import get_settings

logger = structlog.get_logger(__name__)


def _get_priority(item: dict[str, Any]) -> int:
    """
    Assign a 1-5 priority score (1 = Crucial, 5 = Casual) to an evidence item.
    """
    source_type = item.get("source_type")
    if source_type == "auditor_remark":
        return 1
    elif source_type == "image":
        condition = str(item.get("condition", "")).lower()
        if condition in ["critical", "poor"]:
            return 1
        elif condition == "fair":
            return 3
        else:
            return 4
    elif source_type == "document":
        score = item.get("relevance_score") or 0.0
        if score > 0.85:
            return 2
        elif score > 0.75:
            return 3
        elif score > 0.65:
            return 4
        else:
            return 5
    return 5


async def evidence_agent_node(state: AuditState) -> dict[str, Any]:
    """
    Consolidate document, image, and remark evidence into a unified bundle.

    No external API calls are made — this is a pure data transformation node.
    The evidence bundle is sorted by a 5-step priority system to ensure critical
    findings are not dropped when capping to stay within token limits.

    Returns:
        dict with keys: evidence_bundle
    """
    settings = get_settings()

    evidence: list[dict[str, Any]] = []

    try:
        # ── Evidence from retrieved document chunks ───────────────────────────────
        for chunk in state.get("retrieved_chunks", []):
            if not isinstance(chunk, dict):
                logger.warning("invalid_chunk_type", chunk_type=type(chunk).__name__)
                continue
            evidence.append(
                {
                    "source_type": "document",
                    "doc_id": chunk.get("doc_id", "unknown"),
                    "doc_type": chunk.get("doc_type", "unknown"),
                    "filename": chunk.get("filename", "unknown"),
                    "page": chunk.get("page"),
                    "excerpt": str(chunk.get("text", ""))[:400],
                    "finding": f"Relevant clause from {chunk.get('filename', 'unknown')}: {str(chunk.get('text', ''))[:200]}",
                    "relevance_score": chunk.get("score"),
                }
            )

        # ── Evidence from image analyses ──────────────────────────────────────────
        for analysis in state.get("image_analyses", []):
            if not isinstance(analysis, dict):
                logger.warning("invalid_analysis_type", analysis_type=type(analysis).__name__)
                continue
            for finding in analysis.get("findings", []):
                evidence.append(
                    {
                        "source_type": "image",
                        "s3_key": analysis.get("s3_key", "unknown"),
                        "finding": finding,
                        "condition": analysis.get("condition"),
                    }
                )
            if analysis.get("raw_description"):
                evidence.append(
                    {
                        "source_type": "image",
                        "s3_key": analysis.get("s3_key", "unknown"),
                        "finding": f"Image condition [{analysis.get('condition', 'unknown')}]: "
                        f"{str(analysis.get('raw_description', ''))[:300]}",
                        "condition": analysis.get("condition"),
                    }
                )

        # ── Evidence from auditor remarks ─────────────────────────────────────────
        if state.get("auditor_remarks"):
            evidence.append(
                {
                    "source_type": "auditor_remark",
                    "remark_text": state["auditor_remarks"],
                    "finding": f"Auditor observed: {state['auditor_remarks']}",
                }
            )

        # Sort by priority (1 is highest, 5 is lowest)
        evidence.sort(key=_get_priority)
    except Exception as exc:
        logger.error(
            "evidence_agent_error",
            asset_id=state.get("asset_id"),
            error=type(exc).__name__,
            error_msg=str(exc)[:200],
        )
        state.setdefault("errors", []).append(
            f"Evidence agent error: {type(exc).__name__}: {str(exc)[:200]}"
        )

    # Cap the bundle to prevent context window explosion and massive API payloads
    original_count = len(evidence)
    capped_evidence = evidence[: settings.evidence_bundle_cap]
    was_truncated = original_count > settings.evidence_bundle_cap

    if was_truncated:
        logger.warning(
            "evidence_agent_truncated",
            asset_id=state.get("asset_id"),
            original_count=original_count,
            capped_count=len(capped_evidence),
            dropped_count=original_count - len(capped_evidence),
            cap=settings.evidence_bundle_cap,
        )

    logger.info(
        "evidence_agent_complete",
        asset_id=state.get("asset_id"),
        total_evidence_count=original_count,
        capped_evidence_count=len(capped_evidence),
        document_evidence=sum(1 for e in capped_evidence if e["source_type"] == "document"),
        image_evidence=sum(1 for e in capped_evidence if e["source_type"] == "image"),
        remark_evidence=sum(1 for e in capped_evidence if e["source_type"] == "auditor_remark"),
    )
    return {
        "evidence_bundle": capped_evidence,
        "evidence_truncated": was_truncated,
        "evidence_original_count": original_count,
    }
