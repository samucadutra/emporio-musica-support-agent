"""Persistent policy vector index with manifest-based idempotency (design §4, §7 index).

chromadb is used directly because each chunk embeds a title-prefixed text but
stores the plain section text; langchain's Chroma wrapper embeds what it stores.
"""

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import chromadb
from chromadb.config import Settings as ChromaSettings
from langchain_core.embeddings import Embeddings
from pydantic import BaseModel

from emporio_musica_support_agent.rag.chunking import CHUNKER_VERSION, chunk_policy
from emporio_musica_support_agent.rag.extract import extract_policy

COLLECTION = "policies"
MANIFEST_FILE = "manifest.json"
# Fields that decide whether the stored vectors still match the inputs.
COMPARED_FIELDS = ("embedding_model", "pdf_sha256", "chunker_version")


class PolicyChunk(BaseModel):
    section_number: str  # "4.1"
    section_title: str  # "Direito de Arrependimento (Compras Online)"
    parent_title: str | None  # "Política de Trocas e Devoluções"
    text: str
    score: float  # cosine similarity, 0..1


@dataclass(frozen=True)
class IndexStatus:
    state: Literal["missing", "stale", "ok"]
    reason: str | None = None


@dataclass(frozen=True)
class BuildReport:
    built: bool  # False: already up to date, nothing touched
    chunk_count: int
    manifest: dict[str, object]


class IndexNotReadyError(RuntimeError):
    def __init__(self, status: IndexStatus) -> None:
        self.status = status
        detail = f": {status.reason}" if status.reason else ""
        super().__init__(f"policy index is {status.state}{detail}; run `emporio ingest`")


class PolicyIndex:
    def __init__(
        self, chroma_dir: Path, embeddings: Embeddings, pdf_path: Path, embedding_model: str
    ) -> None:
        self.chroma_dir = chroma_dir
        self.embeddings = embeddings
        self.pdf_path = pdf_path
        self.embedding_model = embedding_model

    @property
    def manifest_path(self) -> Path:
        return self.chroma_dir / MANIFEST_FILE

    def _expected(self) -> dict[str, object]:
        return {
            "embedding_model": self.embedding_model,
            "pdf_sha256": hashlib.sha256(self.pdf_path.read_bytes()).hexdigest(),
            "chunker_version": CHUNKER_VERSION,
        }

    def _read_manifest(self) -> dict[str, object] | None:
        if not self.manifest_path.is_file():
            return None
        return json.loads(self.manifest_path.read_text(encoding="utf-8"))

    def status(self) -> IndexStatus:
        """Compare the manifest with the current inputs; never opens Chroma."""
        manifest = self._read_manifest()
        if manifest is None:
            if self.chroma_dir.is_dir() and any(self.chroma_dir.iterdir()):
                # The manifest is written last, so its absence means a build stopped midway.
                return IndexStatus("stale", "manifest missing: interrupted build")
            return IndexStatus("missing")
        expected = self._expected()
        for field in COMPARED_FIELDS:
            if manifest.get(field) != expected[field]:
                return IndexStatus(
                    "stale", f"{field} changed: {manifest.get(field)} -> {expected[field]}"
                )
        return IndexStatus("ok")

    def _client(self) -> chromadb.ClientAPI:
        self.chroma_dir.mkdir(parents=True, exist_ok=True)
        return chromadb.PersistentClient(
            path=str(self.chroma_dir), settings=ChromaSettings(anonymized_telemetry=False)
        )

    def build(self, force: bool = False) -> BuildReport:
        """Rebuild unless up to date. The manifest is written last."""
        if not force and self.status().state == "ok":
            manifest = self._read_manifest() or {}
            return BuildReport(False, int(manifest.get("chunk_count", 0)), manifest)

        self.manifest_path.unlink(missing_ok=True)
        client = self._client()
        if COLLECTION in [c.name for c in client.list_collections()]:
            client.delete_collection(COLLECTION)
        collection = client.create_collection(
            COLLECTION, metadata={"hnsw:space": "cosine"}, embedding_function=None
        )

        chunks = chunk_policy(extract_policy(self.pdf_path))
        collection.add(
            ids=[c.id for c in chunks],
            embeddings=self.embeddings.embed_documents([c.embedding_text for c in chunks]),
            documents=[c.text for c in chunks],
            metadatas=[c.metadata for c in chunks],
        )

        manifest = {
            **self._expected(),
            "chunk_count": len(chunks),
            "built_at": datetime.now(UTC).isoformat(timespec="seconds"),
        }
        self.manifest_path.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        return BuildReport(True, len(chunks), manifest)

    def search(self, query: str, k: int) -> list[PolicyChunk]:
        """The k closest sections, best first. A missing or stale index is never queried."""
        status = self.status()
        if status.state != "ok":
            raise IndexNotReadyError(status)
        collection = self._client().get_collection(COLLECTION, embedding_function=None)
        result = collection.query(
            query_embeddings=[self.embeddings.embed_query(query)],
            n_results=k,
            include=["documents", "metadatas", "distances"],
        )
        documents = (result["documents"] or [[]])[0]
        metadatas = (result["metadatas"] or [[]])[0]
        distances = (result["distances"] or [[]])[0]
        return [
            PolicyChunk(
                section_number=str(metadata["section_number"]),
                section_title=str(metadata["section_title"]),
                parent_title=str(metadata["parent_title"]) or None,
                text=document,
                score=min(1.0, max(0.0, 1.0 - distance)),
            )
            for document, metadata, distance in zip(documents, metadatas, distances, strict=True)
        ]
