"""Unit tests for rule_agent node."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.rule_agent import RulesOutput, rule_agent_node
from app.schemas.audit import TriggeredRule


def _state_overrides() -> dict:
    return {
        "s3_image_keys": ["audits/img.jpg"],
        "auditor_remarks": "Valve cap appears corroded",
        "retrieved_chunks": [
            {
                "doc_id": "manual-v2",
                "doc_type": "user_manual",
                "filename": "pump_manual.pdf",
                "page": 5,
                "text": "Valve pressure must be marked on housing per section 3.2.",
                "score": 0.91,
            }
        ],
        "image_analyses": [
            {
                "s3_key": "audits/img.jpg",
                "findings": ["Pressure label missing from valve"],
                "labels": [],
                "condition": "poor",
                "raw_description": "Pump with missing pressure label.",
            }
        ],
    }


@pytest.mark.asyncio
async def test_rule_agent_happy_path(mock_chat_model, make_audit_state):
    """Happy path: rule_agent should return triggered rules list."""
    rules = [
        TriggeredRule(
            rule_id="valve-pressure-marking",
            rule_description="Valve pressure must be marked on housing.",
            severity="major",
            evidence_refs=[0],
        )
    ]
    mock_structured = AsyncMock()
    mock_structured.ainvoke = AsyncMock(return_value=RulesOutput(triggered_rules=rules))
    mock_chat_model.with_structured_output = MagicMock(return_value=mock_structured)

    with patch("app.agents.rule_agent.get_rule_agent_llm", return_value=mock_chat_model):
        result = await rule_agent_node(make_audit_state(**_state_overrides()))

    assert len(result["triggered_rules"]) == 1
    assert result["triggered_rules"][0]["rule_id"] == "valve-pressure-marking"
    assert len(result["errors"]) == 0


@pytest.mark.asyncio
async def test_rule_agent_no_violations(mock_chat_model, make_audit_state):
    """rule_agent with no violations should return empty list."""
    mock_structured = AsyncMock()
    mock_structured.ainvoke = AsyncMock(return_value=RulesOutput(triggered_rules=[]))
    mock_chat_model.with_structured_output = MagicMock(return_value=mock_structured)

    with patch("app.agents.rule_agent.get_rule_agent_llm", return_value=mock_chat_model):
        result = await rule_agent_node(make_audit_state(**_state_overrides()))

    assert result["triggered_rules"] == []
    assert len(result["errors"]) == 0


@pytest.mark.asyncio
async def test_rule_agent_json_parse_error(mock_chat_model, make_audit_state):
    """Error path: invalid JSON/validation error from LLM should add to errors and return empty rules."""
    mock_structured = AsyncMock()
    mock_structured.ainvoke = AsyncMock(side_effect=ValueError("Validation Error"))
    mock_chat_model.with_structured_output = MagicMock(return_value=mock_structured)

    with patch("app.agents.rule_agent.get_rule_agent_llm", return_value=mock_chat_model):
        result = await rule_agent_node(make_audit_state(**_state_overrides()))

    assert result["triggered_rules"] == []
    assert any("rule_agent" in e for e in result["errors"])


@pytest.mark.asyncio
async def test_rule_agent_llm_failure(mock_chat_model, make_audit_state):
    """Error path: LLM API failure should add to errors and return empty rules."""
    mock_structured = AsyncMock()
    mock_structured.ainvoke = AsyncMock(side_effect=Exception("Anthropic 503"))
    mock_chat_model.with_structured_output = MagicMock(return_value=mock_structured)

    with patch("app.agents.rule_agent.get_rule_agent_llm", return_value=mock_chat_model):
        result = await rule_agent_node(make_audit_state(**_state_overrides()))

    assert result["triggered_rules"] == []
    assert any("rule_agent" in e for e in result["errors"])
