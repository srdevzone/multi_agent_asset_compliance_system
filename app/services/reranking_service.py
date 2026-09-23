"""
Local reranking service using FlashRank (ONNX-based, no PyTorch).

After initial retrieval (dense or hybrid), the reranker re-scores the
top candidates using a cross-encoder model. This acts as a second-pass
filter that improves relevance at zero cost (runs locally, no API key).

FlashRank uses ONNX Runtime and is designed for serverless/edge deployment:
  - ms-marco-TinyBERT-L-2:   ~4MB,  fastest,  NDCG@10: 69.84
  - ms-marco-MiniLM-L-12-v2: ~34MB, fast,     NDCG@10: 74.31 (default)
  - rank-T5-flan:            ~110MB, slower,   best zero-shot accuracy

Integration: called from pinecone_service.smart_query() when
reranking is enabled in settings.
"""

import asyncio
import tempfile
import threading
from typing import Any

import structlog

from app.config import get_settings

logger = structlog.get_logger(__name__)

# Module-level singleton for the FlashRank ranker (lazy-loaded, per-process)
_ranker: Any = None
_ranker_model: str | None = None
_ranker_lock = threading.Lock()


def _get_ranker() -> Any:
    """
    Return the cached FlashRank ranker singleton (lazy-loaded).

    The model is downloaded and cached on first call. Subsequent calls
    reuse the cached model. Uses cache_dir="/opt" for Lambda compatibility.
    """
    global _ranker, _ranker_model
    settings = get_settings()

    # Reload if model changed (e.g., config update)
    if _ranker is not None and _ranker_model == settings.rerank_model:
        return _ranker

    with _ranker_lock:
        if _ranker is not None and _ranker_model == settings.rerank_model:
            return _ranker

        try:
            from flashrank import Ranker

            # /tmp is the only writable cache location in AWS Lambda.
            kwargs: dict[str, Any] = {}
            if _is_lambda():
                kwargs["cache_dir"] = f"{tempfile.gettempdir()}/flashrank"

            _ranker = Ranker(
                model_name=settings.rerank_model,
                max_length=settings.rerank_max_length,
                **kwargs,
            )
            _ranker_model = settings.rerank_model
            logger.info(
                "flashrank_model_loaded",
                model=settings.rerank_model,
                max_length=settings.rerank_max_length,
            )
        except ImportError:
            logger.error(
                "flashrank_not_installed",
                hint="Install with: pip install flashrank",
            )
            raise
        except Exception as exc:
            logger.error(
                "flashrank_load_error",
                model=settings.rerank_model,
                error=type(exc).__name__,
                error_detail=str(exc)[:200],
            )
            raise

    return _ranker


def _is_lambda() -> bool:
    """Detect if running in AWS Lambda environment."""
    import os

    return "AWS_LAMBDA_FUNCTION_NAME" in os.environ


def _rerank_sync(
    query: str,
    documents: list[str],
    top_n: int,
) -> list[dict[str, Any]]:
    """
    Synchronous reranking implementation using FlashRank.

    Called via asyncio.to_thread() from the async wrapper to avoid
    blocking the event loop during model inference.
    """
    try:
        from flashrank import RerankRequest

        ranker = _get_ranker()

        # Build passages in FlashRank format
        passages = [
            {"id": i, "text": doc}
            for i, doc in enumerate(documents)
        ]

        rerank_request = RerankRequest(query=query, passages=passages)
        results = ranker.rerank(rerank_request)

        # Convert to our standard format and take top_n
        enriched = []
        for r in results[:top_n]:
            enriched.append(
                {
                    "index": r["id"],
                    "relevance_score": r["score"],
                    "text": r["text"],
                }
            )

        logger.debug(
            "rerank_complete",
            candidates=len(documents),
            results_returned=len(enriched),
            model=_reranker_model_name(),
        )
        return enriched

    except Exception as exc:
        logger.error(
            "rerank_error",
            error=type(exc).__name__,
            error_detail=str(exc)[:200],
        )
        return []


def _reranker_model_name() -> str:
    """Return the current model name for logging."""
    return _ranker_model or get_settings().rerank_model


async def rerank(
    query: str,
    documents: list[str],
    top_n: int | None = None,
) -> list[dict[str, Any]]:
    """
    Re-rank documents by relevance to the query using FlashRank (local).

    Runs the cross-encoder model in a thread pool to avoid blocking
    the async event loop during inference.

    Args:
        query: The original search query.
        documents: List of document texts to rerank.
        top_n: Number of top results to return (default: from settings).

    Returns:
        List of dicts sorted by relevance (highest first):
        [{"index": int, "relevance_score": float, "text": str}, ...]
        Returns empty list on any error.
    """
    if not documents:
        return []

    settings = get_settings()
    if top_n is None:
        top_n = min(len(documents), settings.rerank_top_n)

    # Run sync model inference in thread pool to avoid blocking
    return await asyncio.to_thread(_rerank_sync, query, documents, top_n)
