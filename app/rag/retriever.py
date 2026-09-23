"""Hybrid retrieval: dense vectors (pgvector) + BM25 keyword scoring, fused with
Reciprocal Rank Fusion. Dense search catches paraphrases ("eat before my
blood test"), BM25 catches exact terms (exam names, insurance plans)."""

import math
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db import is_postgres
from app.models import KnowledgeChunk
from app.privacy import strip_pii
from app.rag.embeddings import Embedder, cosine, get_embedder, stem, tokenize

RRF_K = 60
MIN_TERM_COVERAGE = 0.3


@dataclass
class Hit:
    chunk_id: int
    source: str
    heading: str
    content: str
    score: float
    vector_similarity: float
    keyword_score: float

    @property
    def citation(self) -> str:
        return f"{self.source}#{self.heading}"


def chunk_markdown(text: str) -> list[tuple[str, str]]:
    """Split a markdown document into (heading, body) sections on `##`."""
    chunks: list[tuple[str, str]] = []
    heading, lines = None, []
    for line in text.splitlines():
        if line.startswith("## "):
            if heading and "".join(lines).strip():
                chunks.append((heading, "\n".join(lines).strip()))
            heading, lines = line[3:].strip(), []
        elif heading:
            lines.append(line)
    if heading and "".join(lines).strip():
        chunks.append((heading, "\n".join(lines).strip()))
    return chunks


def index_directory(db: Session, directory: Path, embedder: Embedder | None = None) -> int:
    embedder = embedder or get_embedder()
    db.execute(delete(KnowledgeChunk))
    count = 0
    for path in sorted(directory.glob("*.md")):
        for heading, body in chunk_markdown(path.read_text(encoding="utf-8")):
            db.add(
                KnowledgeChunk(
                    source=path.stem,
                    heading=heading,
                    content=body,
                    embedding=embedder.embed(f"{heading}\n{body}"),
                )
            )
            count += 1
    db.commit()
    return count


class HybridRetriever:
    def __init__(self, db: Session, embedder: Embedder | None = None):
        self.db = db
        self.embedder = embedder or get_embedder()

    def _vector_ranking(self, query_vec: list[float], limit: int) -> list[tuple[KnowledgeChunk, float]]:
        if is_postgres(self.db.get_bind()):
            distance = KnowledgeChunk.embedding.cosine_distance(query_vec)
            rows = self.db.execute(select(KnowledgeChunk, distance.label("d")).order_by(distance).limit(limit)).all()
            return [(chunk, 1 - d) for chunk, d in rows]
        chunks = self.db.scalars(select(KnowledgeChunk)).all()
        scored = [(c, cosine(query_vec, c.embedding)) for c in chunks]
        return sorted(scored, key=lambda x: x[1], reverse=True)[:limit]

    def _bm25_ranking(self, query: str, k1: float = 1.5, b: float = 0.75) -> list[tuple[KnowledgeChunk, float, float]]:
        """Returns (chunk, bm25 score, fraction of query terms matched)."""
        chunks = self.db.scalars(select(KnowledgeChunk)).all()
        if not chunks:
            return []
        # headings are strong topical signals: count them twice
        docs = [[stem(t) for t in tokenize(f"{c.heading} {c.heading} {c.content}")] for c in chunks]
        avgdl = sum(map(len, docs)) / len(docs)
        df = Counter(t for d in docs for t in set(d))
        q_terms = {stem(t) for t in tokenize(query)}
        scored = []
        for chunk, doc in zip(chunks, docs, strict=False):
            tf = Counter(doc)
            score = 0.0
            for term in q_terms & tf.keys():
                idf = math.log(1 + (len(docs) - df[term] + 0.5) / (df[term] + 0.5))
                score += idf * tf[term] * (k1 + 1) / (tf[term] + k1 * (1 - b + b * len(doc) / avgdl))
            if score > 0:
                scored.append((chunk, score, len(q_terms & tf.keys()) / len(q_terms)))
        return sorted(scored, key=lambda x: x[1], reverse=True)

    def search(self, query: str, k: int = 3) -> list[Hit]:
        query = strip_pii(query)  # identifiers carry no retrieval signal, only risk
        query_vec = self.embedder.embed_query(query)
        dense = self._vector_ranking(query_vec, limit=20)
        sparse = self._bm25_ranking(query)[:20]

        fused: dict[int, float] = {}
        by_id: dict[int, KnowledgeChunk] = {}
        sims = {c.id: s for c, s in dense}
        kw = {c.id: (s, cov) for c, s, cov in sparse}
        for ranking in (dense, sparse):
            for rank, (chunk, *_) in enumerate(ranking):
                by_id[chunk.id] = chunk
                fused[chunk.id] = fused.get(chunk.id, 0.0) + 1 / (RRF_K + rank + 1)

        hits = []
        # ties in fused rank are broken by keyword evidence
        for cid, score in sorted(fused.items(), key=lambda x: (x[1], kw.get(x[0], (0, 0))[0]), reverse=True):
            sim, (kws, coverage) = sims.get(cid, 0.0), kw.get(cid, (0.0, 0.0))
            # relevance gate: an out-of-scope query must not get "grounded" on a
            # chunk that shares one incidental word with it
            if sim < self.embedder.min_similarity and coverage < MIN_TERM_COVERAGE:
                continue
            c = by_id[cid]
            hits.append(Hit(c.id, c.source, c.heading, c.content, score, sim, kws))
            if len(hits) == k:
                break
        return hits
