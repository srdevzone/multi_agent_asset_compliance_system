# Reranking

## What is Reranking?

Reranking is a **second-pass relevance filter** that improves search result quality after initial retrieval.

In a typical RAG (Retrieval-Augmented Generation) pipeline:

1. **First retrieval** (fast, approximate): Uses dense vectors (embeddings) or hybrid search to find candidate documents from a vector database like Pinecone. This step is optimized for speed and returns a broader set of candidates (e.g., top 30 results).

2. **Reranking** (slower, accurate): A cross-encoder model re-scores each candidate by jointly analyzing the query and document together. This produces much more accurate relevance scores than comparing pre-computed embeddings.

3. **Final results**: The top-N most relevant documents are returned to the LLM for answer generation.

```
Query → [Dense/Hybrid Search] → Top 30 candidates → [Reranker] → Top 10 most relevant → LLM
```

## Why Does Reranking Help?

### The Problem with Embedding-Based Search

Dense vector search uses **bi-encoders**: the query and document are encoded separately into embeddings, then compared using cosine similarity. This is fast but loses fine-grained semantic relationships because:

- The query and document never "see" each other during encoding
- Subtle nuances like negation, specificity, and context are often lost
- The model must compress all meaning into a fixed-size vector

### How Cross-Encoders Solve This

Rerankers use **cross-encoders**: the query and document are concatenated and processed together through the model. This allows:

- **Joint attention**: The model can attend to query-document interactions directly
- **Better nuance handling**: Negations, specificity, and context are preserved
- **Higher accuracy**: Typically 5-15% improvement in relevance metrics

### Accuracy Benchmarks

| Model | Type | NDCG@10 (TREC DL 19) | MRR@10 (MS Marco) |
|-------|------|---------------------|-------------------|
| Dense search only | Bi-encoder | ~65-70 | ~30-35 |
| + FlashRank TinyBERT-L-2 | Cross-encoder | 69.84 | 32.56 |
| + FlashRank MiniLM-L-12-v2 | Cross-encoder | **74.31** | **39.02** |
| + Cohere rerank-english-v3.0 | Cross-encoder (API) | ~75-77 | ~40 |

> **Note**: NDCG@10 and MRR@10 are standard information retrieval metrics. Higher is better.

## Implementation

### Technology: FlashRank

This project uses **FlashRank** for reranking — a lightweight, local, and free library:

- **No API key required**: Runs entirely locally
- **No PyTorch**: Uses ONNX Runtime (~19MB dependency)
- **Small model**: ~34MB for the recommended model
- **CPU-only**: No GPU required
- **Serverless-friendly**: Designed for Lambda and edge deployment

### Model Options

| Model | Size | Speed | Accuracy | Best For |
|-------|------|-------|----------|----------|
| `ms-marco-TinyBERT-L-2` | ~4MB | Fastest | Good | Latency-critical, resource-constrained |
| `ms-marco-MiniLM-L-12-v2` | ~34MB | Fast | **Best** | **Recommended for most use cases** |
| `rank-T5-flan` | ~110MB | Slower | Best zero-shot | Out-of-domain data |

### Configuration

Reranking is **disabled by default**. Enable via environment variables:

```bash
# Enable reranking
RERANK_ENABLED=true

# Model selection (default: ms-marco-MiniLM-L-12-v2)
RERANK_MODEL=ms-marco-MiniLM-L-12-v2

# Max sequence length (lower = faster, adjust based on chunk size)
RERANK_MAX_LENGTH=128

# Number of candidates to return after reranking
RERANK_TOP_N=10
```

### Resource Usage

| Resource | Value |
|----------|-------|
| Storage | ~34MB (model download, cached after first run) |
| RAM | ~100-150MB when active |
| CPU | Single-threaded inference |
| Cold start | ~1-3 seconds (model loading) |
| Per-query latency | ~50-200ms (depending on candidate count) |

### Deployment Compatibility

| Environment | Compatible? | Notes |
|-------------|-------------|-------|
| AWS Lambda (standard) | Yes | Model fits in 512MB /tmp |
| AWS Lambda (container) | Yes | Use `cache_dir="/opt"` |
| EC2 (1GB RAM) | Yes | ~100-150MB additional RAM |
| EC2 (512MB RAM) | Tight | May cause memory pressure |
| Docker | Yes | Model cached in container |

## How It Works

### Code Flow

```
1. User query arrives
2. Hybrid search retrieves top-K candidates (e.g., 30)
3. If RERANK_ENABLED=true:
   a. FlashRank cross-encoder scores each (query, document) pair
   b. Results sorted by reranker score
   c. Top-N results returned
4. Results passed to LLM for answer generation
```

### Integration Points

- `app/services/reranking_service.py` — FlashRank wrapper with lazy-loaded singleton
- `app/services/pinecone_service.py` — `smart_query()` calls reranker after retrieval
- `app/config.py` — Configuration fields (`rerank_enabled`, `rerank_model`, etc.)

## When to Use Reranking

### Enable reranking when:
- Search relevance is critical (compliance, legal, medical)
- Users expect precise answers, not just "related" documents
- You can tolerate 50-200ms additional latency per query

### Keep reranking disabled when:
- Latency is the top priority (<100ms response time)
- Running on extremely constrained resources (<512MB RAM)
- Initial retrieval quality is already sufficient for your use case

## References

- [FlashRank GitHub](https://github.com/PrithivirajDamodaran/FlashRank)
- [Cross-Encoder MS Marco Models](https://huggingface.co/cross-encoder/ms-marco-MiniLM-L-12-v2)
- [MS Marco Passage Ranking Dataset](https://github.com/microsoft/MSMARCO-Passage-Ranking)
- [TREC Deep Learning Track](https://microsoft.github.io/TREC-2019-Deep-Learning/)
