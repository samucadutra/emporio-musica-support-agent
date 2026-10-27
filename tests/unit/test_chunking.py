"""Heading-aware chunking of the policy text (design §7, chunking)."""

from pathlib import Path

import pytest

from emporio_musica_support_agent.data.loader import policy_path
from emporio_musica_support_agent.rag.chunking import (
    CHUNKER_VERSION,
    MAX_CHUNK_CHARS,
    POLICY_OUTLINE,
    Chunk,
    PolicyOutlineError,
    chunk_policy,
)
from emporio_musica_support_agent.rag.extract import PolicyText, extract_policy

# Top-level sections whose first subsection follows the heading directly.
EMPTY_INTROS = {"5", "6", "8"}


@pytest.fixture(scope="session")
def policy(data_dir: Path) -> PolicyText:
    return extract_policy(policy_path(data_dir))


@pytest.fixture(scope="session")
def chunks(policy: PolicyText) -> list[Chunk]:
    return chunk_policy(policy)


def by_number(chunks: list[Chunk], number: str) -> Chunk:
    return next(c for c in chunks if c.section_number == number)


def test_chunk_count_and_cover(chunks: list[Chunk]) -> None:
    cover = chunks[0]

    assert len(chunks) == 26
    assert (cover.id, cover.section_title, cover.page) == ("sec-0", "Capa", 1)
    assert "MANUAL DE POLÍTICAS E PROCEDIMENTOS" in cover.text


def test_every_outline_heading_is_a_chunk(chunks: list[Chunk]) -> None:
    numbers = {c.section_number for c in chunks}
    expected = {number for number, _ in POLICY_OUTLINE} - EMPTY_INTROS

    assert numbers == expected | {"0"}
    assert {"1", "3", "4", "7"} <= numbers  # intro chunks


def test_ids_unique_and_unsplit(chunks: list[Chunk]) -> None:
    ids = [c.id for c in chunks]

    assert len(ids) == len(set(ids))
    assert all(c.part == 1 and "-p" not in c.id for c in chunks)
    assert by_number(chunks, "4.1").id == "sec-4.1"


def test_numbered_steps_do_not_start_chunks(chunks: list[Chunk]) -> None:
    flow = by_number(chunks, "7.2")

    assert not any("Saudação" in c.section_title for c in chunks)
    assert "1. Saudação" in flow.text
    assert "5. Fechamento" in flow.text  # step 5 is on the next page


def test_table_and_notes_stay_together_across_pages(chunks: list[Chunk]) -> None:
    shipping = by_number(chunks, "5.2")

    assert "PAC (Correios) | 5 a 12 dias úteis" in shipping.text
    assert "O valor do frete" in shipping.text
    assert shipping.page == 4
    assert shipping.parent_title == "Política de Frete e Entregas"


def test_chunks_fit_the_size_limit(chunks: list[Chunk]) -> None:
    assert max(len(c.text) for c in chunks) <= MAX_CHUNK_CHARS


def test_chunking_is_deterministic(policy: PolicyText, chunks: list[Chunk]) -> None:
    assert chunk_policy(policy) == chunks


def test_embedding_text_has_titles(chunks: list[Chunk]) -> None:
    withdrawal = by_number(chunks, "4.1")
    hours = by_number(chunks, "2")

    assert withdrawal.embedding_text.startswith(
        "Seção 4.1 — Direito de Arrependimento (Compras Online) | Política de Trocas e Devoluções\n"
    )
    assert hours.embedding_text.startswith("Seção 2 — Horário de Funcionamento\n")


def test_text_starts_with_heading_line(chunks: list[Chunk]) -> None:
    assert by_number(chunks, "4.1").text.startswith(
        "4.1 Direito de Arrependimento (Compras Online)\n"
    )
    assert by_number(chunks, "9").text.startswith("9. Privacidade e Proteção de Dados\n")


def test_metadata(chunks: list[Chunk]) -> None:
    for chunk in chunks:
        metadata = chunk.metadata

        assert set(metadata) == {
            "section_number",
            "section_title",
            "parent_title",
            "page",
            "part",
            "chunker_version",
        }
        assert None not in metadata.values()
        assert metadata["chunker_version"] == CHUNKER_VERSION


def test_missing_heading_raises(policy: PolicyText) -> None:
    outline = (*POLICY_OUTLINE[:11], ("4.5", "Seção Inventada"), *POLICY_OUTLINE[11:])

    with pytest.raises(PolicyOutlineError, match="4.5 Seção Inventada"):
        chunk_policy(policy, outline)


def test_long_sections_are_split(policy: PolicyText) -> None:
    small = chunk_policy(policy, max_chars=400)
    parts = [c for c in small if c.section_number == "7.1"]

    assert len(parts) >= 2
    assert [c.id for c in parts] == [f"sec-7.1-p{i}" for i in range(1, len(parts) + 1)]
    assert [c.part for c in parts] == list(range(1, len(parts) + 1))
    assert all(c.text.startswith("7.1 Diretrizes de Atendimento\n") for c in parts)
    assert {(c.section_title, c.parent_title, c.page) for c in parts} == {
        ("Diretrizes de Atendimento", "Atendimento via WhatsApp", 6)
    }
    assert max(len(c.text) for c in small) <= 400
