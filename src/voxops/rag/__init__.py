"""
voxops.rag package — Retrieval-Augmented Generation (RAG) Knowledge System.

Public API
----------
DocumentLoader  — loads and chunks text files from the knowledge base.
DocumentChunk   — dataclass representing a single text chunk.
EmbeddingModel  — SentenceTransformers-backed embedding generator.
VectorStore     — ChromaDB-backed persistent vector store.
QueryResult     — dataclass for vector search hits.
Retriever       — high-level RAG retrieval pipeline.
RetrievalResult — packaged retrieval output with context string.
"""

from src.voxops.rag.document_loader import DocumentLoader, DocumentChunk
from src.voxops.rag.embedding_model import EmbeddingModel
from src.voxops.rag.vector_store import VectorStore, QueryResult
from src.voxops.rag.retriever import Retriever, RetrievalResult

__all__ = [
    "DocumentLoader",
    "DocumentChunk",
    "EmbeddingModel",
    "VectorStore",
    "QueryResult",
    "Retriever",
    "RetrievalResult",
]
