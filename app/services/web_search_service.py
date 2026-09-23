"""
Web search fallback service using DuckDuckGo.

Used by the chat agent when Pinecone returns no relevant results
and asset spec metadata is insufficient to answer the question.

The DuckDuckGo client is synchronous, so we run it in a thread
to avoid blocking the asyncio event loop.
"""

from typing import Any, cast

import structlog
from ddgs import DDGS

from app.utils.async_helpers import run_in_thread
from app.utils.resilience import web_search_call

logger = structlog.get_logger(__name__)


def _run_ddg_search(query: str, max_results: int) -> list[dict[str, Any]]:
    """Run the synchronous DDGS text search."""
    with DDGS() as ddgs:
        return list(ddgs.text(query, max_results=max_results))


_run_ddg_search_async = run_in_thread(_run_ddg_search)


@web_search_call
async def _search_internal(query: str, max_results: int) -> list[dict[str, Any]]:
    """Internal search function with retries and circuit breaking."""
    return cast(list[dict[str, Any]], await _run_ddg_search_async(query, max_results))


async def search(query: str, max_results: int = 5) -> list[dict[str, Any]]:
    """
    Perform a web search via DuckDuckGo and return structured results.

    Returns a list of result dicts with keys: url, title, content, score.
    If DuckDuckGo returns no results, or if rate-limited, an empty list is returned.

    Used as the third-tier fallback in the chat endpoint when both Pinecone
    and asset spec context are insufficient to answer the question.
    """
    try:
        ddg_results = await _search_internal(query, max_results)
    except Exception as exc:
        logger.warning("web_search_failed_gracefully", error=type(exc).__name__)
        return []

    results = []
    for r in ddg_results:
        results.append(
            {
                "title": r.get("title", ""),
                "url": r.get("href", ""),
                "content": r.get("body", ""),
                "score": 1.0,
            }
        )

    logger.info("web_search_complete", query=query, results_count=len(results))
    return results
