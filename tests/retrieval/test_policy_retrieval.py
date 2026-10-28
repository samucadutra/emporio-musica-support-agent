"""hit@4 on known policy questions with the real local model (design §13)."""

from pathlib import Path

import pytest

from emporio_musica_support_agent.config import Settings
from emporio_musica_support_agent.data.loader import policy_path
from emporio_musica_support_agent.llm import FastEmbedEmbeddings
from emporio_musica_support_agent.rag.index import PolicyIndex
from emporio_musica_support_agent.tools.policies import search_policies
from emporio_musica_support_agent.tools.schemas import SearchPoliciesInput

pytestmark = pytest.mark.embeddings

# (question as the agent would send it, acceptable sections). The tool asks the
# model to describe the situation, not specifics: a bare city name like
# "Dourados" carries no meaning for the embedding model.
QUESTIONS: list[tuple[str, set[str]]] = [
    ("me arrependi, posso devolver?", {"4.1"}),
    ("posso parcelar em 10x?", {"3.1"}),
    ("qual a garantia?", {"8.1"}),
    ("horário de sábado", {"2"}),
    ("frete para Dourados (outra cidade)", {"5.2"}),
    ("frete grátis em Campo Grande", {"5.1"}),
    ("como rastrear meu pedido", {"5.3"}),
    ("desconto do pix vale na promoção?", {"6.2"}),
    ("o produto veio com defeito", {"4.2"}),
    ("quero trocar por outra cor", {"4.3"}),
    ("vocês vendem cordas?", {"1", "7.1"}),
    ("meus dados pessoais", {"9"}),
]


@pytest.fixture(scope="module")
def index(tmp_path_factory: pytest.TempPathFactory, data_dir: Path) -> PolicyIndex:
    settings = Settings(_env_file=None)
    cache = Path(__file__).parents[2] / settings.models_cache_dir
    embeddings = FastEmbedEmbeddings(settings.embedding_model, cache)
    index = PolicyIndex(
        tmp_path_factory.mktemp("chroma"),
        embeddings,
        policy_path(data_dir),
        settings.embedding_model,
    )
    index.build()
    return index


@pytest.mark.parametrize(("question", "expected"), QUESTIONS)
def test_hit_at_4(index: PolicyIndex, question: str, expected: set[str]) -> None:
    result = search_policies(index, SearchPoliciesInput(question=question, k=4))
    sections = [c.section_number for c in result.chunks]

    assert expected & set(sections), f"{question!r}: got {sections}"
