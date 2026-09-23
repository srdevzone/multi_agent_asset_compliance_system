"""Unit tests for local BM25 scoring."""

import pytest

from app.services.bm25_service import BM25Encoder


def test_bm25_scores_exact_term_match_higher():
    encoder = BM25Encoder().fit(
        ["hydraulic pressure relief valve", "electrical wiring diagram"]
    )

    scores = encoder.score_documents(
        "pressure valve",
        ["hydraulic pressure relief valve", "electrical wiring diagram"],
    )

    assert scores[0] > scores[1]


def test_bm25_requires_fitting():
    with pytest.raises(RuntimeError, match="must be fitted"):
        BM25Encoder().score_documents("query", ["document"])


def test_bm25_empty_corpus_remains_unfitted():
    encoder = BM25Encoder().fit([])

    assert encoder.is_fitted is False


def test_bm25_refit_replaces_old_vocabulary():
    encoder = BM25Encoder().fit(["legacy pressure term"])
    encoder.fit(["current voltage term"])

    assert "legacy" not in encoder.vocabulary
    assert "current" in encoder.vocabulary
