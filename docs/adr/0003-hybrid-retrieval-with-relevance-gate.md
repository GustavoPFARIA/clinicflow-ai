# 0003. Hybrid retrieval (dense + BM25, RRF) with a calibrated relevance gate

**Status:** Accepted

## Context

Clinic FAQs mix paraphrase-heavy questions (*"can I get my money back"*) with exact terms (insurance plan names, exam names). Pure vector search misses rare exact terms; pure keyword search misses paraphrases. Separately, top-k retrieval **always** returns something, so off-topic questions get "grounded" on the nearest random chunk.

## Decision

- Run dense (pgvector cosine) and BM25 rankings and fuse them with Reciprocal Rank Fusion (k = 60). RRF needs no score calibration between the two.
- Drop a hit unless its cosine is at least the provider's `min_similarity` **or** it covers at least 30% of the query terms.
- Set `min_similarity` per embedding model **from measured distributions** (bge-small: in-scope 0.68–0.89, off-topic 0.43–0.57, gate at 0.62).
- Strip PII from queries before retrieval.

## Consequences

- 10/10 top-1 grounding in evals, including paraphrases, and off-topic questions are declined.
- Changing the embedding model requires re-measuring the threshold. This is documented in [RAG](../rag.md#relevance-gate).
- BM25 is computed in-process over all chunks: fine for a clinic-sized knowledge base (tens to low thousands of chunks). A larger corpus would move it to Postgres full-text search.
