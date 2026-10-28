"""Dependency wiring: everything is built once and passed down explicitly (design §2)."""

from dataclasses import dataclass

from langchain_core.embeddings import Embeddings

from emporio_musica_support_agent.clock import Clock, SystemClock
from emporio_musica_support_agent.config import Settings
from emporio_musica_support_agent.data.loader import policy_path
from emporio_musica_support_agent.data.repository import Repository
from emporio_musica_support_agent.llm import FastEmbedEmbeddings
from emporio_musica_support_agent.rag.index import PolicyIndex
from emporio_musica_support_agent.tools.handoff import HandoffLog


@dataclass(frozen=True)
class Deps:
    settings: Settings
    repo: Repository
    policy_index: PolicyIndex
    handoff_log: HandoffLog
    clock: Clock


def build_policy_index(settings: Settings, embeddings: Embeddings) -> PolicyIndex:
    return PolicyIndex(
        settings.chroma_dir, embeddings, policy_path(settings.data_dir), settings.embedding_model
    )


def build_deps(
    settings: Settings, clock: Clock | None = None, embeddings: Embeddings | None = None
) -> Deps:
    """Create the `var/` folders and load data once. Raises DataFileNotFoundError."""
    for directory in (
        settings.var_dir,
        settings.chroma_dir,
        settings.models_cache_dir,
        settings.sqlite_path.parent,
        settings.handoff_log_path.parent,
        settings.log_file.parent,
    ):
        directory.mkdir(parents=True, exist_ok=True)
    if embeddings is None:
        embeddings = FastEmbedEmbeddings(settings.embedding_model, settings.models_cache_dir)
    return Deps(
        settings=settings,
        repo=Repository.load(settings.data_dir),
        policy_index=build_policy_index(settings, embeddings),
        handoff_log=HandoffLog(settings.handoff_log_path),
        clock=clock or SystemClock(),
    )
