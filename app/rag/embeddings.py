"""Embedding providers, selected with EMBEDDING_PROVIDER.

- `fastembed` (default in Docker): BAAI/bge-small-en-v1.5, a real 384-dim
  sentence-embedding model running locally on ONNX. No API key required.
- `hashing` (default in tests/CI): dependency-free, deterministic feature
  hashing. Makes the test suite fast and reproducible.

Both implement the `Embedder` protocol, the seam for a hosted model (Voyage,
OpenAI, Cohere). Each provider carries its own relevance threshold because
cosine scales differ a lot between models.
"""

import hashlib
import math
import re
import unicodedata
from functools import lru_cache
from typing import Protocol

from app.config import get_settings
from app.models import EMBEDDING_DIM

TOKEN_RE = re.compile(r"[a-z0-9]+")

STOPWORDS = frozenset(
    [
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "can",
        "do",
        "does",
        "for",
        "from",
        "how",
        "i",
        "in",
        "is",
        "it",
        "my",
        "of",
        "on",
        "or",
        "the",
        "to",
        "what",
        "when",
        "where",
        "which",
        "who",
        "will",
        "with",
        "you",
        "your",
        "me",
        "we",
        "our",
        "this",
        "that",
        "if",
        "any",
        "get",
        "take",
        "have",
        "has",
        "need",
        "want",
        "please",
        "there",
        "so",
        "not",
        "no",
        "but",
        "all",
        "am",
        "was",
        "were",
        "been",
    ]
)


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in text if not unicodedata.combining(ch)).lower()


def tokenize(text: str) -> list[str]:
    return [t for t in TOKEN_RE.findall(normalize(text)) if t not in STOPWORDS]


def stem(token: str) -> str:
    for suffix in ("ing", "ies", "es", "s", "ed"):
        if token.endswith(suffix) and len(token) - len(suffix) >= 3:
            return token[: -len(suffix)]
    return token


class Embedder(Protocol):
    dim: int
    name: str
    min_similarity: float  # below this a chunk is considered unrelated

    def embed(self, text: str) -> list[float]: ...

    def embed_query(self, text: str) -> list[float]: ...


class HashingEmbedder:
    dim = EMBEDDING_DIM
    name = "hashing"
    min_similarity = 0.3

    def _features(self, text: str) -> list[tuple[str, float]]:
        tokens = [stem(t) for t in tokenize(text)]
        feats: list[tuple[str, float]] = [(f"w:{t}", 1.0) for t in tokens]
        feats += [(f"b:{a}_{b}", 0.7) for a, b in zip(tokens, tokens[1:], strict=False)]
        for t in tokens:
            padded = f"#{t}#"
            feats += [(f"c:{padded[i : i + 3]}", 0.3) for i in range(len(padded) - 2)]
        return feats

    def embed(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        for feat, weight in self._features(text):
            h = int.from_bytes(hashlib.blake2b(feat.encode(), digest_size=8).digest(), "big")
            sign = 1.0 if (h >> 63) & 1 else -1.0
            vec[h % self.dim] += sign * weight
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]

    def embed_query(self, text: str) -> list[float]:
        return self.embed(text)


class FastEmbedEmbedder:
    dim = EMBEDDING_DIM
    name = "bge-small-en-v1.5"
    min_similarity = 0.62

    def __init__(self, model: str = "BAAI/bge-small-en-v1.5"):
        from fastembed import TextEmbedding

        self.model = TextEmbedding(model)

    def embed(self, text: str) -> list[float]:
        return next(iter(self.model.passage_embed([text]))).tolist()

    def embed_query(self, text: str) -> list[float]:
        return next(iter(self.model.query_embed(text))).tolist()


def cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=False))


@lru_cache
def get_embedder() -> Embedder:
    if get_settings().embedding_provider == "fastembed":
        return FastEmbedEmbedder()
    return HashingEmbedder()
