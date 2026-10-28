"""PolicyIndex status, idempotent build and search, with fake embeddings (no download)."""

import json
import shutil
from pathlib import Path

import pytest

from emporio_musica_support_agent.data.loader import policy_path
from emporio_musica_support_agent.rag import index as index_module
from emporio_musica_support_agent.rag.index import IndexNotReadyError, PolicyIndex
from fakes import FakeEmbeddings

MODEL = "fake-model"


def make_index(chroma_dir: Path, pdf: Path, model: str = MODEL) -> PolicyIndex:
    return PolicyIndex(chroma_dir, FakeEmbeddings(), pdf, model)


@pytest.fixture
def pdf(data_dir: Path) -> Path:
    return policy_path(data_dir)


@pytest.fixture
def built(tmp_path: Path, pdf: Path) -> PolicyIndex:
    index = make_index(tmp_path / "chroma", pdf)
    index.build()
    return index


def test_missing_then_built(tmp_path: Path, pdf: Path) -> None:
    index = make_index(tmp_path / "chroma", pdf)

    assert index.status().state == "missing"
    report = index.build()

    assert (report.built, report.chunk_count) == (True, 26)
    assert index.status().state == "ok"
    manifest = json.loads(index.manifest_path.read_text(encoding="utf-8"))
    assert set(manifest) == {
        "embedding_model",
        "pdf_sha256",
        "chunker_version",
        "chunk_count",
        "built_at",
    }
    assert manifest["embedding_model"] == MODEL


def test_second_build_is_a_no_op(built: PolicyIndex) -> None:
    before = (built.manifest_path.stat().st_mtime_ns, built.manifest_path.read_text())

    report = built.build()

    assert (report.built, report.chunk_count) == (False, 26)
    assert (built.manifest_path.stat().st_mtime_ns, built.manifest_path.read_text()) == before


def test_force_rebuilds(built: PolicyIndex) -> None:
    report = built.build(force=True)

    assert report.built
    assert built.status().state == "ok"


def test_changed_model_is_stale(built: PolicyIndex, pdf: Path) -> None:
    status = make_index(built.chroma_dir, pdf, model="other-model").status()

    assert status.state == "stale"
    assert status.reason is not None
    assert "embedding_model" in status.reason


def test_changed_pdf_is_stale(tmp_path: Path, pdf: Path) -> None:
    copy = tmp_path / "policy.pdf"
    shutil.copy(pdf, copy)
    index = make_index(tmp_path / "chroma", copy)
    index.build()

    with copy.open("ab") as f:
        f.write(b"\n")
    status = index.status()

    assert status.state == "stale"
    assert status.reason is not None
    assert "pdf_sha256" in status.reason


def test_changed_chunker_is_stale(built: PolicyIndex, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(index_module, "CHUNKER_VERSION", 99)
    status = built.status()

    assert status.state == "stale"
    assert status.reason is not None
    assert "chunker_version" in status.reason


def test_interrupted_build_is_stale(built: PolicyIndex) -> None:
    built.manifest_path.unlink()
    status = built.status()

    assert status.state == "stale"
    assert status.reason is not None
    assert "interrupted" in status.reason


def test_search_returns_scored_chunks(built: PolicyIndex) -> None:
    results = built.search("direito de arrependimento", k=4)
    scores = [r.score for r in results]

    assert len(results) == 4
    assert results[0].section_number == "4.1"
    assert results[0].parent_title == "Política de Trocas e Devoluções"
    assert scores == sorted(scores, reverse=True)
    assert all(0.0 <= s <= 1.0 for s in scores)


def test_top_level_chunk_has_no_parent(built: PolicyIndex) -> None:
    results = built.search("horário de funcionamento sábado domingo feriados", k=26)
    hours = next(r for r in results if r.section_number == "2")

    assert hours.parent_title is None
    assert hours.text.startswith("2. Horário de Funcionamento\n")


def test_search_refuses_missing_index(tmp_path: Path, pdf: Path) -> None:
    with pytest.raises(IndexNotReadyError, match="missing"):
        make_index(tmp_path / "chroma", pdf).search("garantia", k=4)


def test_search_refuses_stale_index(built: PolicyIndex, pdf: Path) -> None:
    with pytest.raises(IndexNotReadyError, match="stale"):
        make_index(built.chroma_dir, pdf, model="other-model").search("garantia", k=4)
