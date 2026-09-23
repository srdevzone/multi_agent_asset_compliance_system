"""
BM25 sparse vector service for hybrid search.

Provides BM25 scoring to complement dense vector similarity search.
The BM25 encoder builds vocabulary and IDF values from the corpus,
then converts text to sparse vectors for Pinecone hybrid queries.

Score fusion combines dense and BM25 scores:
  final_score = alpha * dense_score + (1 - alpha) * bm25_score

Usage:
    encoder = BM25Encoder()
    encoder.fit(corpus_texts)
    sparse_vector = encoder.encode("query text")
    scores = encoder.score_documents(query, documents)
"""

import json
import math
import re
import threading
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


def _tokenize(text: str) -> list[str]:
    """Tokenize text into lowercase tokens, filtering short tokens."""
    tokens = re.findall(r"\b[a-z0-9]+\b", text.lower())
    return [t for t in tokens if len(t) > 1]


class BM25Encoder:
    """
    BM25 encoder for generating sparse vectors.

    Builds vocabulary and IDF values from a corpus, then encodes
    text into sparse vectors compatible with Pinecone's sparse-dense
    index format.
    """

    def __init__(
        self,
        k1: float = 1.5,
        b: float = 0.75,
        min_token_length: int = 2,
    ) -> None:
        self.k1 = k1
        self.b = b
        self.min_token_length = min_token_length
        self.vocabulary: dict[str, int] = {}
        self.idf: dict[str, float] = {}
        self.avg_doc_length: float = 0.0
        self.doc_count: int = 0
        self._is_fitted: bool = False

    @property
    def is_fitted(self) -> bool:
        """Return True if the encoder has been fitted to a corpus."""
        return self._is_fitted

    def fit(self, corpus: list[str]) -> "BM25Encoder":
        """
        Build vocabulary and IDF from a corpus of texts.

        Args:
            corpus: List of document texts to build the vocabulary from.

        Returns:
            self for method chaining.
        """
        # fit() replaces the prior corpus rather than accidentally accumulating
        # stale vocabulary when an encoder instance is reused.
        self.vocabulary.clear()
        self.idf.clear()
        self.avg_doc_length = 0.0
        self.doc_count = 0
        self._is_fitted = False

        if not corpus:
            logger.warning("bm25_empty_corpus")
            return self

        tokenized_docs = [_tokenize(doc) for doc in corpus]
        self.doc_count = len(tokenized_docs)
        self.avg_doc_length = sum(len(doc) for doc in tokenized_docs) / self.doc_count

        # Build document frequency
        doc_freq: dict[str, int] = {}
        for doc_tokens in tokenized_docs:
            unique_tokens = set(doc_tokens)
            for token in unique_tokens:
                doc_freq[token] = doc_freq.get(token, 0) + 1

        # Build vocabulary and compute IDF
        for token, freq in doc_freq.items():
            if len(token) >= self.min_token_length:
                idx = len(self.vocabulary)
                self.vocabulary[token] = idx
                # BM25 IDF formula: log((N - n + 0.5) / (n + 0.5) + 1)
                self.idf[token] = math.log((self.doc_count - freq + 0.5) / (freq + 0.5) + 1)

        self._is_fitted = True
        logger.info(
            "bm25_fitted",
            corpus_size=self.doc_count,
            vocabulary_size=len(self.vocabulary),
            avg_doc_length=round(self.avg_doc_length, 2),
        )
        return self

    def encode(self, text: str) -> dict[str, Any]:
        """
        Encode text into a BM25 sparse vector.

        Returns a dict with 'indices' and 'values' suitable for
        Pinecone's sparse_values format.
        """
        if not self.is_fitted:
            raise RuntimeError("BM25Encoder must be fitted before encoding")

        tokens = _tokenize(text)
        if not tokens:
            return {"indices": [], "values": []}

        # Count term frequencies
        tf: dict[str, int] = {}
        for token in tokens:
            if token in self.vocabulary:
                tf[token] = tf.get(token, 0) + 1

        indices = []
        values = []
        for token, count in tf.items():
            if token in self.idf:
                idx = self.vocabulary[token]
                # BM25 score for this term
                score = self.idf[token] * (count * (self.k1 + 1)) / (
                    count + self.k1 * (1 - self.b + self.b * len(tokens) / self.avg_doc_length)
                )
                indices.append(idx)
                values.append(score)

        return {"indices": indices, "values": values}

    def score_documents(self, query: str, documents: list[str]) -> list[float]:
        """
        Score documents against a query using BM25.

        Returns a list of scores, one per document.
        """
        if not self.is_fitted:
            raise RuntimeError("BM25Encoder must be fitted before scoring")

        query_tokens = _tokenize(query)
        scores = []

        for doc in documents:
            doc_tokens = _tokenize(doc)
            doc_length = len(doc_tokens)

            # Count term frequencies in document
            tf: dict[str, int] = {}
            for token in doc_tokens:
                if token in self.vocabulary:
                    tf[token] = tf.get(token, 0) + 1

            score = 0.0
            for q_token in query_tokens:
                if q_token in self.idf and q_token in tf:
                    count = tf[q_token]
                    score += self.idf[q_token] * (count * (self.k1 + 1)) / (
                        count
                        + self.k1 * (1 - self.b + self.b * doc_length / self.avg_doc_length)
                    )
            scores.append(score)

        return scores

    def save(self, path: Path) -> None:
        """Persist the encoder to disk as JSON."""
        data = {
            "k1": self.k1,
            "b": self.b,
            "min_token_length": self.min_token_length,
            "vocabulary": self.vocabulary,
            "idf": self.idf,
            "avg_doc_length": self.avg_doc_length,
            "doc_count": self.doc_count,
            "_is_fitted": self._is_fitted,
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2))
        logger.debug("bm25_saved", path=str(path))

    @classmethod
    def load(cls, path: Path) -> "BM25Encoder":
        """Load a persisted encoder from disk."""
        data = json.loads(path.read_text())
        encoder = cls(
            k1=data["k1"],
            b=data["b"],
            min_token_length=data["min_token_length"],
        )
        encoder.vocabulary = data["vocabulary"]
        encoder.idf = data["idf"]
        encoder.avg_doc_length = data["avg_doc_length"]
        encoder.doc_count = data["doc_count"]
        encoder._is_fitted = data["_is_fitted"]
        logger.debug("bm25_loaded", path=str(path))
        return encoder


# Module-level singleton for the BM25 encoder (per-process, Lambda warm start safe)
_bm25_encoder: BM25Encoder | None = None
_bm25_lock: threading.Lock = threading.Lock()


def get_bm25_encoder() -> BM25Encoder:
    """
    Return the cached BM25 encoder singleton (thread-safe).

    Creates a new encoder if none exists. The singleton is per-process
    and safe for Lambda warm starts.
    """
    global _bm25_encoder
    if _bm25_encoder is None:
        with _bm25_lock:
            # Double-checked locking: re-check after acquiring lock
            if _bm25_encoder is None:
                _bm25_encoder = BM25Encoder()
    return _bm25_encoder


def set_bm25_encoder(encoder: BM25Encoder) -> None:
    """
    Set the module-level BM25 encoder singleton (thread-safe).

    Useful for testing or when loading a pre-fitted encoder from disk.
    """
    global _bm25_encoder
    with _bm25_lock:
        _bm25_encoder = encoder


def reset_bm25_encoder() -> None:
    """Reset the singleton to None. Primarily for test isolation (thread-safe)."""
    global _bm25_encoder
    with _bm25_lock:
        _bm25_encoder = None
