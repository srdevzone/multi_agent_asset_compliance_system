"""Unit tests for evidence_agent node."""

import pytest

from app.agents.evidence_agent import evidence_agent_node


def _state_overrides() -> dict:
    return {
        "retrieved_chunks": [
            {
                "doc_id": "manual-v2",
                "doc_type": "user_manual",
                "filename": "pump_manual.pdf",
                "page": 5,
                "text": "Valve pressure must be marked on housing.",
                "score": 0.91,
            }
        ],
        "image_analyses": [
            {
                "s3_key": "audits/img.jpg",
                "findings": ["Missing pressure label"],
                "labels": ["SN-001"],
                "condition": "poor",
                "raw_description": "Pump with missing label.",
            }
        ],
        "auditor_remarks": "The valve cap appears corroded.",
    }


@pytest.mark.asyncio
async def test_evidence_agent_includes_all_source_types(make_audit_state):
    """evidence_agent should produce evidence from documents, images, and remarks."""
    result = await evidence_agent_node(make_audit_state(**_state_overrides()))
    sources = {e["source_type"] for e in result["evidence_bundle"]}
    assert "document" in sources
    assert "image" in sources
    assert "auditor_remark" in sources


@pytest.mark.asyncio
async def test_evidence_agent_document_evidence_fields(make_audit_state):
    """Document evidence should include filename, page, excerpt."""
    result = await evidence_agent_node(make_audit_state(**_state_overrides()))
    doc_evidence = [e for e in result["evidence_bundle"] if e["source_type"] == "document"]
    assert len(doc_evidence) == 1
    assert doc_evidence[0]["filename"] == "pump_manual.pdf"
    assert doc_evidence[0]["page"] == 5
    assert "excerpt" in doc_evidence[0]


@pytest.mark.asyncio
async def test_evidence_agent_image_evidence_fields(make_audit_state):
    """Image evidence should include s3_key and finding."""
    result = await evidence_agent_node(make_audit_state(**_state_overrides()))
    img_evidence = [e for e in result["evidence_bundle"] if e["source_type"] == "image"]
    assert len(img_evidence) >= 1
    assert img_evidence[0]["s3_key"] == "audits/img.jpg"
    assert img_evidence[0]["finding"] == "Missing pressure label"


@pytest.mark.asyncio
async def test_evidence_agent_remark_evidence(make_audit_state):
    """Auditor remark should appear as a single remark evidence item."""
    result = await evidence_agent_node(make_audit_state(**_state_overrides()))
    remark_evidence = [e for e in result["evidence_bundle"] if e["source_type"] == "auditor_remark"]
    assert len(remark_evidence) == 1
    assert "corroded" in remark_evidence[0]["remark_text"]


@pytest.mark.asyncio
async def test_evidence_agent_no_remarks(make_audit_state):
    """Without auditor_remarks, no auditor_remark evidence should appear."""
    overrides = _state_overrides()
    overrides["auditor_remarks"] = None
    result = await evidence_agent_node(make_audit_state(**overrides))
    remark_evidence = [e for e in result["evidence_bundle"] if e["source_type"] == "auditor_remark"]
    assert len(remark_evidence) == 0


@pytest.mark.asyncio
async def test_evidence_agent_empty_state(make_audit_state):
    """evidence_agent with empty lists should return an empty bundle."""
    result = await evidence_agent_node(make_audit_state(retrieved_chunks=[], image_analyses=[]))
    assert result["evidence_bundle"] == []
