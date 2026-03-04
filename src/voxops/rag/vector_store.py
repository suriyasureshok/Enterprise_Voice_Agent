"""
VOXOPS AI Gateway — Vector Store
Persistent ChromaDB-backed vector store for knowledge-base embeddings.
Supports adding, querying, listing, and deleting document chunks.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import chromadb
from chromadb.config import Settings as ChromaSettings
from loguru import logger

from configs.settings import settings
from src.voxops.rag.document_loader import DocumentChunk
from src.voxops.rag.embedding_model import EmbeddingModel


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class QueryResult:
    """A single result returned by a vector similarity search."""
    text: str
    source: str
    chunk_index: int
    distance: float
    chunk_id: str


# ---------------------------------------------------------------------------
# Vector Store
# ---------------------------------------------------------------------------

class VectorStore:
    """
    ChromaDB-backed vector store.

    * Stores document chunks with their embeddings.
    * Supports persistent storage (directory-backed) or ephemeral (in-memory).
    * Uses the shared ``EmbeddingModel`` singleton for encoding.
    """

    _instance: Optional["VectorStore"] = None
    _lock = threading.Lock()

    def __init__(
        self,
        persist_dir: Optional[str] = None,
        collection_name: Optional[str] = None,
        embedding_model: Optional[EmbeddingModel] = None,
        ephemeral: bool = False,
    ) -> None:
        self._persist_dir = persist_dir or settings.chroma_db_path
        self._collection_name = collection_name or settings.chroma_collection_name
        self._embedder = embedding_model or EmbeddingModel.get_instance()
        self._ephemeral = ephemeral

        # Create ChromaDB client
        if ephemeral:
            self._client = chromadb.Client()
            logger.info("VectorStore using ephemeral (in-memory) ChromaDB")
        else:
            Path(self._persist_dir).mkdir(parents=True, exist_ok=True)
            self._client = chromadb.Client(
                ChromaSettings(
                    chroma_db_impl="duckdb+parquet",
                    persist_directory=self._persist_dir,
                    anonymized_telemetry=False,
                )
            )
            logger.info("VectorStore persisting to {}", self._persist_dir)

        # Get or create collection
        self._collection = self._client.get_or_create_collection(
            name=self._collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info(
            "Collection '{}' ready — {} existing documents",
            self._collection_name,
            self._collection.count(),
        )

    # ------------------------------------------------------------------
    # Singleton factory
    # ------------------------------------------------------------------
    @classmethod
    def get_instance(cls, **kwargs) -> "VectorStore":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls(**kwargs)
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Tear down singleton (for testing)."""
        with cls._lock:
            cls._instance = None

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------
    def add_chunks(self, chunks: Sequence[DocumentChunk], batch_size: int = 64) -> int:
        """
        Embed and upsert document chunks into the collection.

        Returns the number of chunks added.
        """
        if not chunks:
            return 0

        texts = [c.text for c in chunks]
        ids = [c.chunk_id for c in chunks]
        metadatas = [
            {"source": c.source, "chunk_index": c.chunk_index}
            for c in chunks
        ]

        # Embed in batches
        embeddings = self._embedder.embed_documents(texts, batch_size=batch_size)

        # Upsert into ChromaDB
        self._collection.upsert(
            ids=ids,
            documents=texts,
            embeddings=embeddings,
            metadatas=metadatas,
        )

        if not self._ephemeral:
            self._persist()

        logger.info("Upserted {} chunks into '{}'", len(chunks), self._collection_name)
        return len(chunks)

    def delete_by_source(self, source: str) -> None:
        """Remove all chunks originating from a specific source file."""
        self._collection.delete(where={"source": source})
        if not self._ephemeral:
            self._persist()
        logger.info("Deleted chunks with source='{}' from '{}'", source, self._collection_name)

    def clear(self) -> None:
        """Delete the collection and recreate it empty."""
        self._client.delete_collection(self._collection_name)
        self._collection = self._client.get_or_create_collection(
            name=self._collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        if not self._ephemeral:
            self._persist()
        logger.info("Cleared collection '{}'", self._collection_name)

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------
    def query(
        self,
        query_text: str,
        top_k: int = 5,
        where: Optional[Dict] = None,
    ) -> List[QueryResult]:
        """
        Perform a similarity search.

        Parameters
        ----------
        query_text : str
            Natural-language query.
        top_k : int
            Number of results to return.
        where : dict, optional
            ChromaDB metadata filter (e.g., ``{"source": "faq.txt"}``).

        Returns
        -------
        List[QueryResult]
        """
        query_embedding = self._embedder.embed_text(query_text)

        kwargs: Dict = {
            "query_embeddings": [query_embedding],
            "n_results": min(top_k, max(self.count(), 1)),
        }
        if where:
            kwargs["where"] = where

        raw = self._collection.query(**kwargs)

        results: List[QueryResult] = []
        if raw["ids"] and raw["ids"][0]:
            for i, doc_id in enumerate(raw["ids"][0]):
                results.append(
                    QueryResult(
                        text=raw["documents"][0][i],
                        source=raw["metadatas"][0][i].get("source", ""),
                        chunk_index=raw["metadatas"][0][i].get("chunk_index", -1),
                        distance=raw["distances"][0][i] if raw.get("distances") else 0.0,
                        chunk_id=doc_id,
                    )
                )
        return results

    def count(self) -> int:
        """Return the total number of stored documents."""
        return self._collection.count()

    def list_sources(self) -> List[str]:
        """Return distinct source file names present in the store."""
        data = self._collection.get(include=["metadatas"])
        sources = sorted({m.get("source", "") for m in (data["metadatas"] or [])})
        return [s for s in sources if s]

    # ------------------------------------------------------------------
    # Persistence helper
    # ------------------------------------------------------------------
    def _persist(self) -> None:
        """Flush to disk (only for persistent mode)."""
        if hasattr(self._client, "persist"):
            self._client.persist()
