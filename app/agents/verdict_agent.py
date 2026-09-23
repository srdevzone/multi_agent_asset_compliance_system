"""
Verdict agent — generate the final structured compliance verdict.

This is the final node in the LangGraph audit pipeline. It synthesises
all prior agent outputs (triggered rules, evidence bundle, previous verdicts)
into a structured JSON compliance verdict.

On success, the verdict is returned as a dict matching the internal schema.
On failure, a minimal INSUFFICIENT_DATA verdict is returned so the response
is always well-formed regardless of LLM errors.

Populates: state["verdict"]
"""

import json
from typing import Any, Literal

import structlog
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from app.agents.state import AuditState, get_asset_spec_dict
from app.dependencies import get_verdict_agent_llm
from app.utils.llm import call_structured_llm
from app.utils.retry import llm_retry
from app.utils.time import utc_now_iso

logger = structlog.get_logger(__name__)


class VerdictOutput(BaseModel):
    compliance_status: Literal["COMPLIANT", "NON_COMPLIANT", "NEEDS_REVIEW", "INSUFFICIENT_DATA"]
    confidence: float = Field(ge=0.0, le=1.0)
    recommendations: list[str]
    verdict_reasoning: str
    change_summary: str | None = Field(
        default=None,
        description="Summary of changes from previous verdict if this is a re-audit",
    )
    rules_newly_triggered: list[str] | None = Field(
        default=None,
        description="Rules that were NOT triggered in the previous verdict but are now triggered",
    )
    rules_resolved: list[str] | None = Field(
        default=None,
        description="Rules that WERE triggered in the previous verdict but are now resolved",
    )


_VERDICT_SYSTEM_PROMPT = (
    "You are a senior compliance engineer issuing a formal audit verdict. "
    "Be precise, evidence-based, and actionable. "
    "Never speculate beyond the evidence provided. "
    "Reference specific document clauses and image findings in your reasoning."
)

_VERDICT_PROMPT_TEMPLATE = """Based on the following audit evidence, issue a formal compliance verdict.

ASSET: {asset_name} (ID: {asset_id})

TRIGGERED RULES:
{triggered_rules}

EVIDENCE BUNDLE:
{evidence_bundle}

PREVIOUS VERDICTS (for trend-aware reasoning and re-audit comparison):
{previous_verdicts}

INSTRUCTIONS:
1. Issue a compliance status (COMPLIANT, NON_COMPLIANT, NEEDS_REVIEW, or INSUFFICIENT_DATA).
2. Provide confidence level and reasoning based on the evidence.
3. If previous verdicts exist, compare the current findings against them:
   - Identify rules that are newly triggered (not in previous verdict)
   - Identify rules that have been resolved (were triggered before, now compliant)
   - Provide a change summary describing the overall trend (improving, stable, declining)
4. Use INSUFFICIENT_DATA if there is not enough evidence to reach a reliable conclusion."""


@llm_retry
async def _call_verdict_llm(llm: Any, messages: list[BaseMessage]) -> VerdictOutput:
    """Helper to call verdict agent LLM with circuit breaker."""
    return await call_structured_llm(llm, VerdictOutput, messages, "llm_verdict")


def _build_insufficient_data_verdict(
    state: AuditState,
    recommendations: list[str],
    reasoning: str,
    errors: list[str],
    generated_at: str,
    *,
    triggered_rules: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "asset_id": state["asset_id"],
        "run_id": state["run_id"],
        "compliance_status": "INSUFFICIENT_DATA",
        "confidence": 0.0,
        "triggered_rules": triggered_rules
        if triggered_rules is not None
        else state.get("triggered_rules", []),
        "evidence": state.get("evidence_bundle", []),
        "recommendations": recommendations,
        "verdict_reasoning": reasoning,
        "documents_consulted": state.get("documents_consulted", []),
        "generated_at": generated_at,
        "errors": errors if errors else None,
    }


async def verdict_agent_node(state: AuditState) -> dict[str, Any]:
    """
    Generate the final compliance compliance verdict using structured output.
    """
    llm = get_verdict_agent_llm()
    new_errors: list[str] = []
    cumulative_errors: list[str] = list(state.get("errors", []))
    generated_at = utc_now_iso()

    try:
        asset_spec_dict = get_asset_spec_dict(state)
        asset_name = asset_spec_dict.get("name") or "Unknown Asset"

        # Check if there are no document embeddings found in the system for this asset
        retrieved_chunks = state.get("retrieved_chunks", [])
        if not retrieved_chunks:
            no_docs_error = "No reference compliance document embeddings found in the vector database for this asset namespace."
            if no_docs_error not in cumulative_errors:
                cumulative_errors.append(no_docs_error)
            new_errors.append(no_docs_error)

            verdict = _build_insufficient_data_verdict(
                state=state,
                recommendations=[
                    "No compliance reference documents or vector embeddings were found for this asset in the vector database.",
                    "Please upload and ingest reference documentation (such as user manuals, safety sheets, or compliance specification documents) before initiating the audit pipeline.",
                ],
                reasoning=(
                    f"Compliance audit aborted: No reference document embeddings found in the vector database for Asset '{asset_name}' "
                    f"(ID: '{state['asset_id']}'). Active compliance auditing requires pre-existing reference standards to cross-reference against visual evidence."
                ),
                errors=cumulative_errors,
                generated_at=generated_at,
                triggered_rules=[],
            )
            logger.info(
                "verdict_agent_no_embeddings_fallback",
                asset_id=state["asset_id"],
                run_id=state["run_id"],
                compliance_status=verdict["compliance_status"],
                reason="No embeddings found for asset namespace",
            )
            return {"verdict": verdict, "errors": new_errors}

        prompt = _VERDICT_PROMPT_TEMPLATE.format(
            asset_name=asset_name,
            asset_id=state["asset_id"],
            triggered_rules=json.dumps(state.get("triggered_rules", []), indent=2),
            evidence_bundle=json.dumps(state.get("evidence_bundle", []), indent=2),
            previous_verdicts=json.dumps(state.get("previous_verdicts") or [], indent=2),
        )

        messages = [
            SystemMessage(content=_VERDICT_SYSTEM_PROMPT),
            HumanMessage(content=prompt),
        ]

        parsed_obj: VerdictOutput = await _call_verdict_llm(llm, messages)
        parsed = parsed_obj.model_dump()

        verdict = {
            "asset_id": state["asset_id"],
            "run_id": state["run_id"],
            "compliance_status": parsed["compliance_status"],
            "confidence": float(parsed["confidence"]),
            "triggered_rules": state.get("triggered_rules", []),
            "evidence": state.get("evidence_bundle", []),
            "recommendations": parsed.get("recommendations", []),
            "verdict_reasoning": parsed.get("verdict_reasoning", ""),
            "documents_consulted": state.get("documents_consulted", []),
            "generated_at": generated_at,
            "errors": cumulative_errors if cumulative_errors else None,
            # Re-audit diff fields
            "change_summary": parsed.get("change_summary"),
            "rules_newly_triggered": parsed.get("rules_newly_triggered"),
            "rules_resolved": parsed.get("rules_resolved"),
            "is_re_audit": bool(state.get("previous_verdicts")),
        }

        logger.info(
            "verdict_agent_complete",
            asset_id=state["asset_id"],
            run_id=state["run_id"],
            compliance_status=verdict["compliance_status"],
            confidence=verdict["confidence"],
            rules_triggered=len(state.get("triggered_rules", [])),
        )
        return {"verdict": verdict, "errors": new_errors}

    except Exception as exc:
        logger.error("verdict_agent_error", error=type(exc).__name__)
        err_msg = f"verdict_agent: {exc}"
        new_errors.append(err_msg)
        cumulative_errors.append(err_msg)

    # Fallback verdict — always return a well-formed response
    fallback_verdict = _build_insufficient_data_verdict(
        state=state,
        recommendations=["Manual review required — automated analysis could not complete."],
        reasoning="The automated verdict generation encountered an error. Manual review is required.",
        errors=cumulative_errors,
        generated_at=generated_at,
    )
    return {"verdict": fallback_verdict, "errors": new_errors}
