# Retrieval Pipeline

This document describes the retrieval path shared by the audit Document Agent and auditor chat.

## Pipeline overview

```text
PDF page
  → parent chunks (context)
  → child chunks (embedded in Pinecone)

Query
  → dense Pinecone candidate retrieval
  → BM25 scoring over the candidate text
  → normalized dense/BM25 score fusion
  → optional FlashRank cross-encoder reranking
  → top-K child matches with parent context
  → audit rule prompt or chat prompt
```

The implementation entry point is `app.services.pinecone_service.smart_query()`.

## Parent-document retrieval

Parent-document retrieval (PDR) is enabled by default. During PDF ingestion:

1. Each page is divided into large parent chunks.
2. Each parent is divided into smaller overlapping child chunks.
3. Only child text is embedded and searched.
4. Each child's Pinecone metadata includes its parent text.
5. Prompt formatting includes the matched child and its broader parent context.

This gives retrieval the precision of small chunks while preserving enough context for compliance interpretation.

| Variable | Default | Purpose |
|---|---:|---|
| `PDR_ENABLED` | `true` | Enable parent/child chunking |
| `PDR_PARENT_CHUNK_SIZE` | `2048` | Parent context size in characters |
| `PDR_CHILD_CHUNK_SIZE` | `256` | Embedded child size in characters |
| `PDR_CHILD_OVERLAP` | `32` | Overlap between child chunks |

When PDR is disabled, ingestion uses `CHUNK_SIZE` and `CHUNK_OVERLAP` for flat chunking.

## Hybrid candidate scoring

Hybrid search is enabled by default. Pinecone first returns a broad dense candidate set (up to three times the requested retrieval count, capped at 100). The service then:

1. Fits BM25 to the current candidate texts.
2. Scores the candidates against the raw query text.
3. Min-max normalizes the dense and BM25 scores independently.
4. Computes the fused score:

```text
fused_score = HYBRID_ALPHA × normalized_dense
            + (1 - HYBRID_ALPHA) × normalized_bm25
```

The BM25 model is query-local. It is not shared between assets and does not depend on process warm state, so Lambda cold starts do not disable hybrid scoring.

> This is candidate-level hybrid fusion, not Pinecone sparse-vector retrieval. BM25 can reorder the dense candidate set but cannot introduce a document that was absent from that set.

| Variable | Default | Purpose |
|---|---:|---|
| `HYBRID_SEARCH_ENABLED` | `true` | Enable BM25/dense fusion |
| `HYBRID_ALPHA` | `0.7` | Dense contribution to the fused score |
| `BM25_K1` | `1.5` | BM25 term-frequency saturation |
| `BM25_B` | `0.75` | BM25 document-length normalization |

Set `HYBRID_SEARCH_ENABLED=false` to use dense Pinecone results directly.

## Optional cross-encoder reranking

Reranking is disabled by default. When enabled, `smart_query()` retrieves at least `RERANK_TOP_N` candidates and passes them to FlashRank. The cross-encoder jointly evaluates each query/document pair, reorders the candidates, and returns the caller's requested top-K.

| Variable | Default | Purpose |
|---|---:|---|
| `RERANK_ENABLED` | `false` | Enable local FlashRank reranking |
| `RERANK_MODEL` | `ms-marco-MiniLM-L-12-v2` | FlashRank model |
| `RERANK_MAX_LENGTH` | `128` | Maximum model sequence length |
| `RERANK_TOP_N` | `10` | Minimum candidate pool considered before final top-K selection |

The model is lazy-loaded and cached per process. AWS Lambda uses `/tmp/flashrank`, while other environments use FlashRank's default cache. If reranking fails, retrieval safely falls back to the pre-reranked order.

See [RERANKING_SERVICE.md](RERANKING_SERVICE.md) for model and resource details.

## Scores and chat fallback

Result dictionaries may include:

- `score`: current ordering score (fused score, or reranker score when enabled)
- `dense_score`: original Pinecone similarity for hybrid results
- `bm25_score`: raw BM25 score for hybrid results
- `retrieval_score`: pre-reranking ordering score when reranking runs
- `rerank_score`: FlashRank relevance score when reranking succeeds

Chat's `0.75` document-relevance threshold remains calibrated to the original dense Pinecone similarity. It does **not** compare the threshold against normalized fusion or FlashRank scores.

## Operational notes

- Existing vectors must be re-ingested to gain PDR `parent_text` metadata. Old vectors remain searchable but cannot provide expanded parent context.
- Changing PDR chunk settings affects future ingestion only; re-ingest documents to rebuild existing chunks.
- Larger reranking pools improve recall but increase CPU time and request latency.
- Parent text increases Pinecone metadata size and LLM prompt size. Keep parent chunks within Pinecone metadata and model-context limits.
