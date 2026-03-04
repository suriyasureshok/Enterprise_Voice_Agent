"""
VOXOPS AI Gateway — Retriever
Orchestrates the full RAG retrieval pipeline:
  query → embed → vector search → format context for LLM.

Also provides a high-level ``ingest_knowledge_base()`` helper that
loads, chunks, embeds, and stores the entire knowledge base in one call.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from loguru import logger

from configs.settings import settings
from src.voxops.rag.document_loader import DocumentLoader, DocumentChunk
from src.voxops.rag.embedding_model import EmbeddingModel
from src.voxops.rag.vector_store import VectorStore, QueryResult


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class RetrievalResult:
    """Packaged result of a retrieval query."""
    query: str
    passages: List[QueryResult]
    context_text: str  # ready-to-use LLM context string
    num_sources: int = 0
    sources: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Retriever
# ---------------------------------------------------------------------------

class Retriever:
    """
    High-level RAG retriever.

    Typical usage::

        retriever = Retriever.get_instance()
        retriever.ingest_knowledge_base()          # one-time
        result = retriever.retrieve("How do I track a shipment?")
        print(result.context_text)   # inject into LLM prompt
    """

    _instance: Optional["Retriever"] = None

    def __init__(
        self,
        vector_store: Optional[VectorStore] = None,
        embedding_model: Optional[EmbeddingModel] = None,
        document_loader: Optional[DocumentLoader] = None,
        top_k: int = 5,
        max_context_chars: int = 3000,
    ) -> None:
        self._store = vector_store or VectorStore.get_instance()
        self._embedder = embedding_model or EmbeddingModel.get_instance()
        self._loader = document_loader or DocumentLoader()
        self.top_k = top_k
        self.max_context_chars = max_context_chars
        logger.info("Retriever initialised — top_k={}, max_context_chars={}", top_k, max_context_chars)

    # ------------------------------------------------------------------
    # Singleton
    # ------------------------------------------------------------------
    @classmethod
    def get_instance(cls, **kwargs) -> "Retriever":
        if cls._instance is None:
            cls._instance = cls(**kwargs)
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        cls._instance = None

    # ------------------------------------------------------------------
    # Ingestion
    # ------------------------------------------------------------------
    def ingest_knowledge_base(self, force: bool = False) -> int:
        """
        Load all knowledge-base documents, chunk them, embed, and store.

        Parameters
        ----------
        force : bool
            If True, clear existing vectors before re-ingesting.

        Returns
        -------
        int
            Total number of chunks ingested.
        """
        if force:
            logger.info("Force re-ingestion — clearing vector store")
            self._store.clear()

        if not force and self._store.count() > 0:
            logger.info(
                "Vector store already contains {} documents — skipping ingestion "
                "(use force=True to re-ingest)",
                self._store.count(),
            )
            return self._store.count()

        chunks = self._loader.load_documents()
        if not chunks:
            logger.warning("No documents found for ingestion")
            return 0

        added = self._store.add_chunks(chunks)
        logger.info("Knowledge-base ingestion complete — {} chunks stored", added)
        return added

    def ingest_file(self, filename: str) -> int:
        """Ingest (or re-ingest) a single knowledge-base file."""
        self._store.delete_by_source(filename)
        chunks = self._loader.load_single(filename)
        added = self._store.add_chunks(chunks)
        logger.info("Ingested {} chunks from {}", added, filename)
        return added

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------
    def retrieve(
        self,
        query: str,
        top_k: Optional[int] = None,
        source_filter: Optional[str] = None,
    ) -> RetrievalResult:
        """
        Retrieve relevant context for a user query.

        Parameters
        ----------
        query : str
            Natural-language query.
        top_k : int, optional
            Override the default number of results.
        source_filter : str, optional
            Restrict search to a specific source file.

        Returns
        -------
        RetrievalResult
        """
        k = top_k or self.top_k
        where = {"source": source_filter} if source_filter else None

        passages = self._store.query(query_text=query, top_k=k, where=where)

        # Build a context string that fits within max_context_chars
        context_parts: List[str] = []
        total_chars = 0
        sources_seen: set = set()

        for p in passages:
            snippet = f"[Source: {p.source}]\n{p.text}"
            if total_chars + len(snippet) > self.max_context_chars:
                break
            context_parts.append(snippet)
            total_chars += len(snippet)
            sources_seen.add(p.source)

        context_text = "\n\n---\n\n".join(context_parts)
        sources_list = sorted(sources_seen)

        result = RetrievalResult(
            query=query,
            passages=passages,
            context_text=context_text,
            num_sources=len(sources_list),
            sources=sources_list,
        )

        logger.debug(
            "Retrieved {} passages ({} chars) from {} sources for query: '{}'",
            len(passages),
            total_chars,
            result.num_sources,
            query[:80],
        )
        return result

    def retrieve_context_string(
        self,
        query: str,
        top_k: Optional[int] = None,
        source_filter: Optional[str] = None,
    ) -> str:
        """Convenience method — returns just the context string."""
        return self.retrieve(query, top_k, source_filter).context_text

    # ------------------------------------------------------------------
    # Inspection helpers
    # ------------------------------------------------------------------
    def store_count(self) -> int:
        """Number of vectors currently in the store."""
        return self._store.count()

    def list_indexed_sources(self) -> List[str]:
        """Return list of source filenames currently in the vector store."""
        return self._store.list_sources()
