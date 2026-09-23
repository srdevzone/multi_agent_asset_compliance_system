"""
Service-specific resilience decorator factories.

Combines circuit-breaker + tenacity retry into single decorators
for each downstream service to eliminate duplicated stacking.
"""

from collections.abc import Callable
from typing import Any, ParamSpec, TypeVar, cast

from tenacity import retry, stop_after_attempt, wait_exponential

from app.utils.circuit_breaker import circuit_breaker

P = ParamSpec("P")
T = TypeVar("T")


def _compose(*decorators: Callable[[Any], Any]) -> Callable[[Any], Any]:
    """Compose multiple decorators — outermost first."""

    def composed(func: Callable[..., Any]) -> Callable[..., Any]:
        result = func
        for dec in reversed(decorators):
            result = dec(result)
        return result

    return composed


def pinecone_call(func: Callable[P, T]) -> Callable[P, T]:
    cb = circuit_breaker("pinecone", failure_threshold=3, recovery_timeout=30)
    rt = retry(
        stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), reraise=True
    )
    return cast(Callable[P, T], _compose(cb, rt)(func))


def s3_call(func: Callable[P, T]) -> Callable[P, T]:
    cb = circuit_breaker("s3", failure_threshold=3, recovery_timeout=30)
    rt = retry(
        stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), reraise=True
    )
    return cast(Callable[P, T], _compose(cb, rt)(func))


def dynamodb_call(func: Callable[P, T]) -> Callable[P, T]:
    rt = retry(
        stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=5), reraise=True
    )
    return rt(func)


def embedding_call(func: Callable[P, T]) -> Callable[P, T]:
    rt = retry(
        stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8), reraise=True
    )
    return rt(func)


def web_search_call(func: Callable[P, T]) -> Callable[P, T]:
    cb = circuit_breaker("ddg", failure_threshold=2, recovery_timeout=120)
    rt = retry(
        stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=1, max=5), reraise=True
    )
    return cast(Callable[P, T], _compose(cb, rt)(func))
