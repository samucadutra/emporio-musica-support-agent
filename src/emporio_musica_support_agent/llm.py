"""LLM layer: local embeddings (design §4). The chat model factory comes later."""

from functools import cached_property
from pathlib import Path

from fastembed import TextEmbedding
from langchain_core.embeddings import Embeddings


class FastEmbedEmbeddings(Embeddings):
    """LangChain `Embeddings` over a local fastembed ONNX model; no API key needed.

    The model loads on first use, so building dependencies or checking the index
    status never triggers the download (~220 MB, cached in `cache_dir`).
    """

    def __init__(self, model_name: str, cache_dir: Path) -> None:
        self.model_name = model_name
        self.cache_dir = cache_dir

    @cached_property
    def _model(self) -> TextEmbedding:
        return TextEmbedding(model_name=self.model_name, cache_dir=str(self.cache_dir))

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [vector.tolist() for vector in self._model.embed(texts)]

    def embed_query(self, text: str) -> list[float]:
        return next(iter(self._model.query_embed(text))).tolist()
