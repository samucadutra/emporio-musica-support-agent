"""search_policies tool (design §6.5)."""

import pytest
from pydantic import ValidationError

from emporio_musica_support_agent.rag.index import PolicyChunk
from emporio_musica_support_agent.tools.policies import search_policies
from emporio_musica_support_agent.tools.schemas import SearchPoliciesInput


def chunk(number: str, score: float) -> PolicyChunk:
    return PolicyChunk(
        section_number=number, section_title="Título", parent_title=None, text="…", score=score
    )


class FakeSearcher:
    def __init__(self, chunks: list[PolicyChunk]) -> None:
        self.chunks = chunks
        self.calls: list[tuple[str, int]] = []

    def search(self, query: str, k: int) -> list[PolicyChunk]:
        self.calls.append((query, k))
        return self.chunks


def test_chunks_sorted_best_first() -> None:
    searcher = FakeSearcher([chunk("5.1", 0.2), chunk("4.1", 0.9), chunk("4.2", 0.5)])

    result = search_policies(searcher, SearchPoliciesInput(question="devolução", k=3))

    assert [c.section_number for c in result.chunks] == ["4.1", "4.2", "5.1"]
    assert searcher.calls == [("devolução", 3)]


def test_k_defaults_to_four() -> None:
    assert SearchPoliciesInput(question="garantia").k == 4


@pytest.mark.parametrize("k", [0, 9])
def test_k_out_of_range(k: int) -> None:
    with pytest.raises(ValidationError):
        SearchPoliciesInput(question="garantia", k=k)


def test_docstring_guides_the_model() -> None:
    doc = search_policies.__doc__ or ""

    assert "(seção 4.1)" in doc
    assert "frete para outra cidade" in doc
