"""
Pinecone vector database service.

Namespace convention: asset_{asset_uuid}
All documents for one asset share one namespace.
Documents within the namespace are distinguished by doc_id metadata.

Retrieval modes:
  - Broad (audit / chat): top-k across entire namespace, no filter
  - Filtered (update / delete): filter on doc_id to scope to one document
  - Hybrid (BM25 + Dense): combines dense similarity with keyword matching

All public functions include tenacity retry logic for transient API errors.
"""

from typing import Any

import structlog
from pinecone import Index
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import get_settings
from app.services.bm25_service import BM25Encoder
from app.services.reranking_service import rerank
from app.utils.circuit_breaker import circuit_breaker

logger = structlog.get_logger(__name__)


def _normalize_scores(scores: list[float]) -> list[float]:
    """Normalize scores to [0, 1] range using min-max normalization."""
    if not scores:
        return scores
    min_score = min(scores)
    max_score = max(scores)
    score_range = max_score - min_score
    if score_range == 0:
        return [1.0] * len(scores)
    return [(s - min_score) / score_range for s in scores]


def _namespace(asset_id: str) -> str:
    """Construct the Pinecone namespace key for an asset."""
    return f"asset_{asset_id}"


@circuit_breaker("pinecone", failure_threshold=3, recovery_timeout=30)
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    reraise=True,
)
def upsert_vectors(
    index: Index,
    asset_id: str,
    vectors: list[dict[str, Any]],  # [{"id": str, "values": list[float], "metadata": dict}]
) -> int:
    """
    Upsert a batch of vectors into the asset's Pinecone namespace.

    Vectors are batched in groups of 100 to stay within the Pinecone API
    request size limits. Returns the total number of vectors upserted.
    Retries up to 3 times with exponential backoff on transient errors.
    """
    namespace = _namespace(asset_id)
    batch_size = 100
    total = 0
    for i in range(0, len(vectors), batch_size):
        batch = vectors[i : i + batch_size]
        index.upsert(vectors=batch, namespace=namespace)
        total += len(batch)
        logger.debug(
            "pinecone_batch_upserted",
            namespace=namespace,
            batch_size=len(batch),
            offset=i,
        )
    logger.info("pinecone_upsert_complete", namespace=namespace, total_vectors=total)
    return total


@circuit_breaker("pinecone", failure_threshold=3, recovery_timeout=30)
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    reraise=True,
)
def delete_by_doc_id(index: Index, asset_id: str, doc_id: str) -> int:
    """
    Delete all vectors belonging to a specific document within an asset namespace.

    Used on update events to remove stale vectors before re-embedding.
    The deletion is scoped to the asset namespace, so other documents
    in the same namespace are never affected.

    Returns the count of deleted vectors (best-effort from stats diff).
    """
    namespace = _namespace(asset_id)
    prefix = f"{asset_id}_{doc_id}_"
    deleted_count = 0

    for ids_batch in index.list(prefix=prefix, namespace=namespace):
        if ids_batch:
            index.delete(ids=ids_batch, namespace=namespace)
            deleted_count += len(ids_batch)

    logger.info(
        "pinecone_delete_complete",
        namespace=namespace,
        doc_id=doc_id,
        vectors_deleted=deleted_count,
    )
    return deleted_count


@circuit_breaker("pinecone", failure_threshold=3, recovery_timeout=30)
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    reraise=True,
)
def query_namespace(
    index: Index,
    asset_id: str,
    query_vector: list[float],
    top_k: int,
    doc_type_filter: str | None = None,
) -> list[dict[str, Any]]:
    """
    Query the asset's Pinecone namespace for semantically relevant chunks.

    By default (doc_type_filter=None), searches across ALL documents in the
    namespace so every document type (user_manual, safety_sheet, etc.) can
    contribute to the result set.

    Pass doc_type_filter to restrict retrieval to a specific document type.
    Returns a list of result dicts with keys: id, score, metadata.
    """
    namespace = _namespace(asset_id)
    query_filter = None
    if doc_type_filter:
        query_filter = {"doc_type": {"$eq": doc_type_filter}}

    response = index.query(
        vector=query_vector,
        top_k=top_k,
        namespace=namespace,
        include_metadata=True,
        filter=query_filter,
    )

    results = [
        {
            "id": match.id,
            "score": match.score,
            "metadata": match.metadata or {},
        }
        for match in response.matches
    ]
    logger.debug(
        "pinecone_query_complete",
        namespace=namespace,
        top_k=top_k,
        results_returned=len(results),
        doc_type_filter=doc_type_filter,
    )
    return results


def query_namespace_hybrid(
    index: Index,
    asset_id: str,
    query_vector: list[float],
    query_text: str,
    top_k: int,
    doc_type_filter: str | None = None,
    alpha: float | None = None,
) -> list[dict[str, Any]]:
    """
    Query with hybrid search combining dense vectors and BM25 sparse scoring.

    The underlying Pinecone request already owns retry and circuit-breaker
    behavior through query_namespace(); this local fusion layer deliberately
    does not wrap it again.

    Uses score fusion: final_score = alpha * dense_score + (1 - alpha) * bm25_score

    Args:
        index: Pinecone index client
        asset_id: Asset UUID for namespace
        query_vector: Dense embedding vector for the query
        query_text: Raw query text for BM25 scoring
        top_k: Number of results to return
        doc_type_filter: Optional filter on document type
        alpha: Weight for dense score (0.0-1.0). If None, uses config default.

    Returns:
        List of result dicts with fused scores: id, score, metadata
    """
    settings = get_settings()
    if alpha is None:
        alpha = settings.hybrid_alpha

    # Step 1: Get a broader dense candidate set. BM25 is applied to this set,
    # so the encoder is fitted per query rather than kept as mutable process
    # state (which would be lost on cold starts and leak vocabulary across assets).
    dense_results = query_namespace(
        index, asset_id, query_vector, min(top_k * 3, 100), doc_type_filter
    )

    if not dense_results:
        return []

    # Step 2: Fit and score BM25 over this query's candidate corpus.
    candidate_texts = [r["metadata"].get("text", "") for r in dense_results]
    bm25 = BM25Encoder(k1=settings.bm25_k1, b=settings.bm25_b).fit(candidate_texts)
    bm25_scores = bm25.score_documents(query_text, candidate_texts)

    # Step 3: Normalize both score sets to [0, 1] range
    dense_scores = [r["score"] for r in dense_results]
    normalized_dense = _normalize_scores(dense_scores)
    normalized_bm25 = _normalize_scores(bm25_scores)

    # Step 4: Compute fused scores
    fused_results = []
    for i, result in enumerate(dense_results):
        fused_score = alpha * normalized_dense[i] + (1 - alpha) * normalized_bm25[i]

        fused_results.append(
            {
                "id": result["id"],
                "score": fused_score,
                "metadata": result["metadata"],
                "dense_score": dense_scores[i],
                "bm25_score": bm25_scores[i],
            }
        )

    # Step 5: Sort by fused score and return top_k
    fused_results.sort(key=lambda x: x["score"], reverse=True)
    top_results = fused_results[:top_k]

    logger.debug(
        "pinecone_hybrid_query_complete",
        namespace=_namespace(asset_id),
        top_k=top_k,
        alpha=alpha,
        candidates=len(dense_results),
        results_returned=len(top_results),
        doc_type_filter=doc_type_filter,
    )
    return top_results


async def smart_query(
    index: Index,
    asset_id: str,
    query_vector: list[float],
    query_text: str,
    top_k: int,
    doc_type_filter: str | None = None,
) -> list[dict[str, Any]]:
    """
    Query with automatic dispatch between hybrid and dense-only search,
    followed by optional local reranking as a second-pass relevance filter.

    Retrieval flow:
      1. Initial retrieval — hybrid (BM25 + dense) or dense-only
      2. (optional) Reranking — FlashRank cross-encoder re-scores top candidates
      3. Return top_k results sorted by final relevance

    This is the recommended query function for callers that don't need
    fine-grained control over the search mode.
    """
    settings = get_settings()

    # Retrieve a wider candidate pool when reranking is enabled. The reranker
    # then reduces it to the caller-requested top_k.
    retrieval_k = max(top_k, settings.rerank_top_n) if settings.rerank_enabled else top_k

    # Step 1: Initial retrieval
    if settings.hybrid_search_enabled:
        results = query_namespace_hybrid(
            index, asset_id, query_vector, query_text, retrieval_k, doc_type_filter
        )
    else:
        results = query_namespace(index, asset_id, query_vector, retrieval_k, doc_type_filter)

    if not results:
        return results

    # Step 2: Optional local reranking (FlashRank, no API key needed)
    if settings.rerank_enabled:
        candidate_texts = [r["metadata"].get("text", "") for r in results]
        reranked = await rerank(
            query=query_text,
            documents=candidate_texts,
            top_n=top_k,
        )
        if reranked:
            # Reorder results by reranker relevance score
            valid_reranked = [
                r
                for r in reranked
                if isinstance(r.get("index"), int) and 0 <= r["index"] < len(results)
            ]
            reranked_indices = [r["index"] for r in valid_reranked]
            reranked_results = [results[i] for i in reranked_indices]
            # Overwrite scores with reranker relevance scores
            for i, r in enumerate(valid_reranked):
                reranked_results[i]["retrieval_score"] = reranked_results[i]["score"]
                reranked_results[i]["score"] = r["relevance_score"]
                reranked_results[i]["rerank_score"] = r["relevance_score"]
            results = reranked_results

            logger.debug(
                "smart_query_reranked",
                namespace=_namespace(asset_id),
                top_k=top_k,
                before=len(candidate_texts),
                after=len(results),
            )

    return results[:top_k]


def namespace_has_docs(index: Index, asset_id: str) -> bool:
    """Return True if this asset's namespace already contains vectors."""
    stats = index.describe_index_stats()
    ns = stats.namespaces.get(_namespace(asset_id))
    return ns is not None and getattr(ns, "vector_count", 0) > 0


def doc_id_exists(index: Index, asset_id: str, doc_id: str) -> bool:
    """Return True if vectors with this doc_id already exist in the namespace."""
    namespace = _namespace(asset_id)
    prefix = f"{asset_id}_{doc_id}_"
    
    try:
        generator = index.list(prefix=prefix, namespace=namespace)
        for ids_batch in generator:
            if ids_batch:
                return True
    except Exception as e:
        logger.warning("doc_id_exists_list_error", error=str(e))
        
    return False


@circuit_breaker("pinecone", failure_threshold=3, recovery_timeout=30)
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    reraise=True,
)
def delete_namespace(index: Index, asset_id: str) -> int:
    """
    Delete ALL vectors in an asset's Pinecone namespace.

    Used by the admin delete endpoint for GDPR right-to-erasure.  Deletes
    every vector regardless of doc_type or doc_id.  The namespace itself
    is implicitly removed once it contains zero vectors.

    Returns the number of vectors deleted (best-effort via stats diff).
    """
    namespace = _namespace(asset_id)

    # Snapshot count before deletion
    stats_before = index.describe_index_stats()
    ns_before = stats_before.namespaces.get(namespace, {})
    count_before = getattr(ns_before, "vector_count", 0)

    if count_before == 0:
        logger.info("pinecone_namespace_already_empty", namespace=namespace)
        return 0

    # Delete all vectors in the namespace
    index.delete(delete_all=True, namespace=namespace)

    logger.info(
        "pinecone_namespace_deleted",
        namespace=namespace,
        vectors_deleted=count_before,
    )
    return count_before
