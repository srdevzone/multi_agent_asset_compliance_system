"""Unit tests for the optional FlashRank wrapper."""

from unittest.mock import MagicMock, patch

import pytest

from app.services import reranking_service


@pytest.mark.asyncio
async def test_rerank_returns_ranked_indices_without_blocking_interface():
    ranker = MagicMock()
    ranker.rerank.return_value = [
        {"id": 1, "score": 0.95, "text": "relevant"},
        {"id": 0, "score": 0.25, "text": "less relevant"},
    ]

    with patch("app.services.reranking_service._get_ranker", return_value=ranker):
        results = await reranking_service.rerank(
            "pressure limit", ["less relevant", "relevant"], top_n=1
        )

    assert results == [{"index": 1, "relevance_score": 0.95, "text": "relevant"}]


@pytest.mark.asyncio
async def test_rerank_empty_documents_skips_model():
    with patch("app.services.reranking_service._get_ranker") as get_ranker:
        results = await reranking_service.rerank("query", [])

    assert results == []
    get_ranker.assert_not_called()
