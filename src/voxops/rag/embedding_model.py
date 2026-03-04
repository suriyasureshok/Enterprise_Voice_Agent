"""
VOXOPS AI Gateway — Embedding Model
Wraps SentenceTransformers to produce dense vector embeddings for text chunks.
Thread-safe singleton ensures the model is loaded only once.
"""

from __future__ import annotations

import threading
from typing import List, Optional, Sequence

import numpy as np
from loguru import logger

from configs.settings import settings


class EmbeddingModel:
    """Lazy-loading, thread-safe wrapper around a SentenceTransformers model."""

    _instance: Optional["EmbeddingModel"] = None
    _lock = threading.Lock()

    def __init__(self, model_name: Optional[str] = None) -> None:
        self._model_name = model_name or settings.embedding_model_name
        self._model = None  # lazy-loaded
        self._dimension: Optional[int] = None
        logger.info("EmbeddingModel created — model_name={}", self._model_name)

    # ------------------------------------------------------------------
    # Singleton factory
    # ------------------------------------------------------------------
    @classmethod
    def get_instance(cls, model_name: Optional[str] = None) -> "EmbeddingModel":
        """Return (or create) the global singleton instance."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls(model_name)
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Tear down singleton — useful for testing."""
        with cls._lock:
            cls._instance = None

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------
    def _ensure_loaded(self) -> None:
        """Load the model if it hasn't been loaded yet."""
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            logger.info("Loading SentenceTransformer model '{}' …", self._model_name)
            self._model = SentenceTransformer(self._model_name)
            # Probe dimension with a dummy embed
            probe = self._model.encode(["hello"])
            self._dimension = int(probe.shape[1])
            logger.info(
                "Model loaded — dimension={}", self._dimension
            )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dimension(self) -> int:
        """Return embedding dimensionality (loads model if needed)."""
        self._ensure_loaded()
        assert self._dimension is not None
        return self._dimension

    def embed_text(self, text: str) -> List[float]:
        """Embed a single string and return a list of floats."""
        self._ensure_loaded()
        assert self._model is not None
        vector = self._model.encode([text])[0]
        return vector.tolist()

    def embed_documents(self, texts: Sequence[str], batch_size: int = 64) -> List[List[float]]:
        """
        Embed a batch of strings.

        Parameters
        ----------
        texts : Sequence[str]
            The texts to embed.
        batch_size : int
            Encoding batch size passed to SentenceTransformers.

        Returns
        -------
        List[List[float]]
            One embedding per input text.
        """
        self._ensure_loaded()
        assert self._model is not None
        if not texts:
            return []
        logger.debug("Embedding {} documents (batch_size={})", len(texts), batch_size)
        vectors = self._model.encode(list(texts), batch_size=batch_size, show_progress_bar=False)
        return [v.tolist() for v in vectors]

    def cosine_similarity(self, vec_a: List[float], vec_b: List[float]) -> float:
        """Compute cosine similarity between two embedding vectors."""
        a = np.asarray(vec_a, dtype=np.float32)
        b = np.asarray(vec_b, dtype=np.float32)
        dot = float(np.dot(a, b))
        norm = float(np.linalg.norm(a) * np.linalg.norm(b))
        if norm == 0.0:
            return 0.0
        return dot / norm
