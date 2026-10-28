"""Test doubles shared across test modules (importable via pytest's `pythonpath`)."""

import hashlib
import math

from langchain_core.embeddings import Embeddings

from emporio_musica_support_agent.text import fold


class FakeEmbeddings(Embeddings):
    """Deterministic hashed bag of words: texts sharing words get similar vectors.

    No model download. Short words ("de", "a", "em") are skipped so they don't
    dominate the overlap, and 1024 buckets keep word collisions rare.
    """

    dimensions = 1024

    def _vector(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        for word in (w for w in fold(text).split() if len(w) >= 4):
            bucket = int(hashlib.md5(word.encode()).hexdigest(), 16) % self.dimensions
            vector[bucket] += 1.0
        norm = math.sqrt(sum(v * v for v in vector)) or 1.0
        return [v / norm for v in vector]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vector(text)
