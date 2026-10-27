"""Real local-embedding index build (downloads the model once into var/models)."""

from pathlib import Path

import pytest

from emporio_musica_support_agent.config import Settings
from emporio_musica_support_agent.data.loader import policy_path
from emporio_musica_support_agent.llm import FastEmbedEmbeddings
from emporio_musica_support_agent.rag.index import PolicyIndex

pytestmark = pytest.mark.embeddings


@pytest.fixture(scope="module")
def embeddings() -> FastEmbedEmbeddings:
    settings = Settings(_env_file=None)
    # Shared cache, so the ~220 MB model downloads only once across runs.
    cache = Path(__file__).parents[2] / settings.models_cache_dir
    return FastEmbedEmbeddings(settings.embedding_model, cache)


@pytest.fixture(scope="module")
def index(
    tmp_path_factory: pytest.TempPathFactory, embeddings: FastEmbedEmbeddings, data_dir: Path
) -> PolicyIndex:
    chroma_dir = tmp_path_factory.mktemp("chroma")
    return PolicyIndex(chroma_dir, embeddings, policy_path(data_dir), embeddings.model_name)


def test_embedding_dimensions(embeddings: FastEmbedEmbeddings) -> None:
    assert len(embeddings.embed_query("teste")) == 384
    assert len(embeddings.embed_documents(["um", "dois"])) == 2


def test_real_build(index: PolicyIndex) -> None:
    report = index.build()

    assert report.chunk_count == 26
    assert index.status().state == "ok"


def test_withdrawal_question_finds_section_4_1(index: PolicyIndex) -> None:
    index.build()
    results = index.search("me arrependi, posso devolver o produto?", k=4)

    assert "4.1" in [r.section_number for r in results]
