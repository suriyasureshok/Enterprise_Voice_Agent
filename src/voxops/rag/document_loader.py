"""
VOXOPS AI Gateway — Document Loader
Loads text files from the knowledge-base directory and splits them into
semantically meaningful chunks for embedding and vector storage.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Sequence

from loguru import logger

from configs.settings import settings


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DocumentChunk:
    """One chunk of text with metadata."""
    text: str
    source: str  # originating filename
    chunk_index: int
    chunk_id: str = field(default="")  # deterministic hash-based ID

    def __post_init__(self) -> None:
        if not self.chunk_id:
            digest = hashlib.sha256(
                f"{self.source}::{self.chunk_index}::{self.text[:64]}".encode()
            ).hexdigest()[:16]
            # frozen dataclass → use object.__setattr__
            object.__setattr__(self, "chunk_id", f"{self.source}_{self.chunk_index}_{digest}")


# ---------------------------------------------------------------------------
# Splitter helpers
# ---------------------------------------------------------------------------

def _split_by_sections(text: str, chunk_size: int = 500, chunk_overlap: int = 50) -> List[str]:
    """
    Split text into chunks.  The algorithm first tries to respect double-newline
    paragraph boundaries.  If a paragraph exceeds *chunk_size* it is further split
    on single newlines.  Finally, any remaining oversized segment is hard-split on
    whitespace so that every chunk stays ≤ *chunk_size* characters.
    
    An *overlap* of the last N characters is prepended to each subsequent chunk
    to maintain context continuity across boundaries.
    """
    paragraphs = text.split("\n\n")
    raw_segments: List[str] = []

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        if len(para) <= chunk_size:
            raw_segments.append(para)
        else:
            # Try splitting on single newline
            lines = para.split("\n")
            buffer = ""
            for line in lines:
                candidate = f"{buffer}\n{line}".strip() if buffer else line.strip()
                if len(candidate) <= chunk_size:
                    buffer = candidate
                else:
                    if buffer:
                        raw_segments.append(buffer)
                    # Hard-split very long lines on whitespace
                    if len(line) > chunk_size:
                        words = line.split()
                        buf = ""
                        for w in words:
                            test = f"{buf} {w}".strip()
                            if len(test) <= chunk_size:
                                buf = test
                            else:
                                if buf:
                                    raw_segments.append(buf)
                                buf = w
                        if buf:
                            raw_segments.append(buf)
                        buffer = ""
                    else:
                        buffer = line.strip()
            if buffer:
                raw_segments.append(buffer)

    # Now apply overlap between consecutive segments
    if chunk_overlap <= 0 or len(raw_segments) <= 1:
        return raw_segments

    chunks: List[str] = [raw_segments[0]]
    for seg in raw_segments[1:]:
        prev = chunks[-1]
        overlap_text = prev[-chunk_overlap:] if len(prev) >= chunk_overlap else prev
        chunks.append(f"{overlap_text} {seg}".strip())
    return chunks


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class DocumentLoader:
    """Loads and chunks text files from the knowledge-base directory."""

    SUPPORTED_EXTENSIONS = {".txt", ".md"}

    def __init__(
        self,
        knowledge_dir: Optional[Path] = None,
        chunk_size: int = 500,
        chunk_overlap: int = 50,
    ) -> None:
        self.knowledge_dir = knowledge_dir or settings.knowledge_base_dir
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        logger.info(
            "DocumentLoader initialised — dir={}, chunk_size={}, overlap={}",
            self.knowledge_dir,
            self.chunk_size,
            self.chunk_overlap,
        )

    # --------------------------------------------------
    # Internal helpers
    # --------------------------------------------------
    def _list_files(self) -> List[Path]:
        """Return sorted list of supported files in the knowledge-base dir."""
        if not self.knowledge_dir.exists():
            logger.warning("Knowledge-base directory does not exist: {}", self.knowledge_dir)
            return []
        files = sorted(
            p
            for p in self.knowledge_dir.iterdir()
            if p.is_file() and p.suffix.lower() in self.SUPPORTED_EXTENSIONS
        )
        logger.debug("Found {} knowledge-base files", len(files))
        return files

    def _load_single_file(self, path: Path) -> str:
        """Read a single text file and return its content."""
        text = path.read_text(encoding="utf-8")
        logger.debug("Loaded {} ({} chars)", path.name, len(text))
        return text

    # --------------------------------------------------
    # Public methods
    # --------------------------------------------------
    def load_documents(self) -> List[DocumentChunk]:
        """Load all documents, split into chunks, return list of DocumentChunks."""
        all_chunks: List[DocumentChunk] = []
        files = self._list_files()

        if not files:
            logger.warning("No knowledge-base documents found in {}", self.knowledge_dir)
            return all_chunks

        for fp in files:
            text = self._load_single_file(fp)
            pieces = _split_by_sections(text, self.chunk_size, self.chunk_overlap)
            for idx, piece in enumerate(pieces):
                chunk = DocumentChunk(
                    text=piece,
                    source=fp.name,
                    chunk_index=idx,
                )
                all_chunks.append(chunk)

        logger.info(
            "Loaded {} chunks from {} documents",
            len(all_chunks),
            len(files),
        )
        return all_chunks

    def load_single(self, filename: str) -> List[DocumentChunk]:
        """Load and chunk a specific file by name."""
        fp = self.knowledge_dir / filename
        if not fp.exists():
            raise FileNotFoundError(f"Knowledge-base file not found: {fp}")
        text = self._load_single_file(fp)
        pieces = _split_by_sections(text, self.chunk_size, self.chunk_overlap)
        chunks = [
            DocumentChunk(text=piece, source=fp.name, chunk_index=idx)
            for idx, piece in enumerate(pieces)
        ]
        logger.info("Loaded {} chunks from {}", len(chunks), filename)
        return chunks

    def list_sources(self) -> List[str]:
        """Return the names of all available knowledge-base files."""
        return [p.name for p in self._list_files()]
