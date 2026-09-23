"""
Structured-output LLM call helper.

Eliminates duplicated circuit-breaker + structured-output patterns
across image, rule, and verdict agents.
"""

from collections.abc import Sequence
from typing import TypeVar, cast

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage

from app.utils.circuit_breaker import circuit_breaker

T = TypeVar("T")


async def call_structured_llm(
    llm: BaseChatModel,
    output_model: type[T],
    messages: Sequence[BaseMessage],
    circuit_name: str,
    *,
    failure_threshold: int = 3,
    recovery_timeout: int = 60,
) -> T:
    structured_llm = llm.with_structured_output(output_model)
    cb = circuit_breaker(
        circuit_name, failure_threshold=failure_threshold, recovery_timeout=recovery_timeout
    )
    return cast(T, await cb(structured_llm.ainvoke)(messages))
