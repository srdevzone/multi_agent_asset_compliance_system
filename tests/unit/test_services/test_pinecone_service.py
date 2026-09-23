"""Unit tests for pinecone_service — all Pinecone calls mocked."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import pinecone_service


def test_upsert_vectors_batches_correctly(mock_pinecone_index):
    """upsert_vectors should batch in groups of 100 and return the total count."""
    vectors = [
        {"id": f"vec_{i}", "values": [0.1] * 1536, "metadata": {"doc_id": "doc-1"}}
        for i in range(250)
    ]
    result = pinecone_service.upsert_vectors(mock_pinecone_index, "asset-abc", vectors)
    assert result == 250
    # 250 vectors / 100 per batch = 3 upsert calls
    assert mock_pinecone_index.upsert.call_count == 3


def test_upsert_vectors_small_batch(mock_pinecone_index):
    """upsert_vectors with fewer than 100 vectors should make exactly one call."""
    vectors = [
        {"id": f"vec_{i}", "values": [0.1] * 1536, "metadata": {"doc_id": "doc-1"}}
        for i in range(50)
    ]
    result = pinecone_service.upsert_vectors(mock_pinecone_index, "asset-abc", vectors)
    assert result == 50
    assert mock_pinecone_index.upsert.call_count == 1


def test_delete_by_doc_id_calls_correct_filter(mock_pinecone_index):
    """delete_by_doc_id must list ids by prefix and delete them."""
    mock_pinecone_index.list.return_value = iter([["vec1", "vec2"]])
    
    deleted = pinecone_service.delete_by_doc_id(mock_pinecone_index, "abc", "manual-v2")
    
    mock_pinecone_index.list.assert_called_once_with(
        prefix="abc_manual-v2_",
        namespace="asset_abc"
    )
    mock_pinecone_index.delete.assert_called_once_with(
        ids=["vec1", "vec2"],
        namespace="asset_abc",
    )
    assert deleted == 2


def test_delete_by_doc_id_returns_zero_when_namespace_empty(mock_pinecone_index):
    """delete_by_doc_id should return 0 when list yields nothing."""
    mock_pinecone_index.list.return_value = iter([])
    deleted = pinecone_service.delete_by_doc_id(mock_pinecone_index, "abc", "doc-1")
    assert deleted == 0
    assert mock_pinecone_index.delete.call_count == 0


def test_query_namespace_applies_doc_type_filter(mock_pinecone_index):
    """query_namespace must apply the doc_type filter when provided."""
    pinecone_service.query_namespace(
        mock_pinecone_index,
        "abc",
        [0.1] * 1536,
        top_k=5,
        doc_type_filter="safety_sheet",
    )
    call_kwargs = mock_pinecone_index.query.call_args.kwargs
    assert call_kwargs["filter"] == {"doc_type": {"$eq": "safety_sheet"}}


def test_query_namespace_no_filter_by_default(mock_pinecone_index):
    """query_namespace without doc_type_filter must NOT include a filter."""
    pinecone_service.query_namespace(mock_pinecone_index, "abc", [0.1] * 1536, top_k=5)
    call_kwargs = mock_pinecone_index.query.call_args.kwargs
    assert call_kwargs.get("filter") is None


def test_namespace_has_docs_true(mock_pinecone_index):
    """namespace_has_docs returns True when namespace has vectors."""
    mock_pinecone_index.describe_index_stats.return_value = MagicMock(
        namespaces={"asset_abc": MagicMock(vector_count=5)}
    )
    assert pinecone_service.namespace_has_docs(mock_pinecone_index, "abc") is True


def test_namespace_has_docs_false_empty_namespace(mock_pinecone_index):
    """namespace_has_docs returns False when namespace doesn't exist."""
    mock_pinecone_index.describe_index_stats.return_value = MagicMock(namespaces={})
    assert pinecone_service.namespace_has_docs(mock_pinecone_index, "abc") is False


def test_hybrid_query_fits_bm25_from_current_candidates():
    dense_results = [
        {"id": "semantic", "score": 0.9, "metadata": {"text": "general instructions"}},
        {"id": "keyword", "score": 0.8, "metadata": {"text": "pressure valve limit"}},
    ]
    settings = SimpleNamespace(hybrid_alpha=0.2, bm25_k1=1.5, bm25_b=0.75)

    with (
        patch("app.services.pinecone_service.get_settings", return_value=settings),
        patch("app.services.pinecone_service.query_namespace", return_value=dense_results),
    ):
        results = pinecone_service.query_namespace_hybrid(
            MagicMock(), "abc", [0.1], "pressure valve", top_k=2
        )

    assert results[0]["id"] == "keyword"
    assert results[0]["bm25_score"] > results[1]["bm25_score"]


@pytest.mark.asyncio
async def test_smart_query_retrieves_wider_pool_for_reranking():
    candidates = [
        {"id": str(i), "score": 0.9 - i / 100, "metadata": {"text": f"text {i}"}}
        for i in range(10)
    ]
    settings = SimpleNamespace(
        hybrid_search_enabled=False,
        rerank_enabled=True,
        rerank_top_n=10,
    )
    reranked = [
        {"index": 9, "relevance_score": 0.99, "text": "text 9"},
        {"index": 0, "relevance_score": 0.9, "text": "text 0"},
    ]

    with (
        patch("app.services.pinecone_service.get_settings", return_value=settings),
        patch(
            "app.services.pinecone_service.query_namespace", return_value=candidates
        ) as query,
        patch(
            "app.services.pinecone_service.rerank", new=AsyncMock(return_value=reranked)
        ),
    ):
        results = await pinecone_service.smart_query(
            MagicMock(), "abc", [0.1], "query", top_k=2
        )

    assert query.call_args.args[3] == 10
    assert [result["id"] for result in results] == ["9", "0"]
    assert results[0]["retrieval_score"] == candidates[9]["retrieval_score"]
