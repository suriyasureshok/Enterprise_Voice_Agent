"""
VOXOPS AI Gateway — Phase 6 RAG Knowledge System Tests
Comprehensive tests for document_loader, embedding_model, vector_store, and retriever.
"""

import sys, os, shutil, tempfile, textwrap
from pathlib import Path

import pytest

# Ensure project root on path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# ======================================================================
# Fixtures
# ======================================================================

@pytest.fixture
def tmp_kb(tmp_path):
    """Create a temporary knowledge-base directory with sample files."""
    kb = tmp_path / "knowledge_base"
    kb.mkdir()

    (kb / "policies.txt").write_text(textwrap.dedent("""\
        COMPANY POLICIES

        1. DELIVERY TIMEFRAMES
           - Standard delivery: 3-5 business days
           - Express delivery: 1-2 business days

        2. RETURNS
           - Items may be returned within 30 days.
           - Refunds are processed within 5 business days.
    """), encoding="utf-8")

    (kb / "faq.txt").write_text(textwrap.dedent("""\
        FAQ

        Q: How do I track my order?
        A: Use your tracking ID on the web portal or ask the voice agent.

        Q: What does delayed status mean?
        A: Your package has been delayed due to traffic or weather.
    """), encoding="utf-8")

    return kb


@pytest.fixture(autouse=True)
def reset_singletons():
    """Reset all module singletons before each test."""
    from src.voxops.rag.embedding_model import EmbeddingModel
    from src.voxops.rag.vector_store import VectorStore
    from src.voxops.rag.retriever import Retriever
    EmbeddingModel.reset()
    VectorStore.reset()
    Retriever.reset()
    yield
    EmbeddingModel.reset()
    VectorStore.reset()
    Retriever.reset()


# ======================================================================
# 1. Document Loader Tests
# ======================================================================

class TestDocumentLoader:
    """Tests for document_loader.py"""

    def test_load_documents_from_kb(self, tmp_kb):
        from src.voxops.rag.document_loader import DocumentLoader

        loader = DocumentLoader(knowledge_dir=tmp_kb, chunk_size=500, chunk_overlap=50)
        chunks = loader.load_documents()

        assert len(chunks) > 0, "Should produce at least one chunk"
        # We have two files
        sources = {c.source for c in chunks}
        assert "policies.txt" in sources
        assert "faq.txt" in sources

    def test_chunk_ids_are_unique(self, tmp_kb):
        from src.voxops.rag.document_loader import DocumentLoader

        loader = DocumentLoader(knowledge_dir=tmp_kb)
        chunks = loader.load_documents()
        ids = [c.chunk_id for c in chunks]
        assert len(ids) == len(set(ids)), "All chunk IDs must be unique"

    def test_chunk_has_metadata(self, tmp_kb):
        from src.voxops.rag.document_loader import DocumentLoader

        loader = DocumentLoader(knowledge_dir=tmp_kb)
        chunks = loader.load_documents()
        for c in chunks:
            assert c.source, "source should not be empty"
            assert c.chunk_index >= 0
            assert c.text.strip(), "text should not be empty"
            assert c.chunk_id, "chunk_id should not be empty"

    def test_load_single_file(self, tmp_kb):
        from src.voxops.rag.document_loader import DocumentLoader

        loader = DocumentLoader(knowledge_dir=tmp_kb)
        chunks = loader.load_single("faq.txt")
        assert len(chunks) > 0
        for c in chunks:
            assert c.source == "faq.txt"

    def test_load_single_nonexistent_raises(self, tmp_kb):
        from src.voxops.rag.document_loader import DocumentLoader

        loader = DocumentLoader(knowledge_dir=tmp_kb)
        with pytest.raises(FileNotFoundError):
            loader.load_single("missing.txt")

    def test_list_sources(self, tmp_kb):
        from src.voxops.rag.document_loader import DocumentLoader

        loader = DocumentLoader(knowledge_dir=tmp_kb)
        sources = loader.list_sources()
        assert "policies.txt" in sources
        assert "faq.txt" in sources

    def test_empty_directory(self, tmp_path):
        from src.voxops.rag.document_loader import DocumentLoader

        empty = tmp_path / "empty_kb"
        empty.mkdir()
        loader = DocumentLoader(knowledge_dir=empty)
        chunks = loader.load_documents()
        assert chunks == []

    def test_nonexistent_directory(self, tmp_path):
        from src.voxops.rag.document_loader import DocumentLoader

        loader = DocumentLoader(knowledge_dir=tmp_path / "nope")
        chunks = loader.load_documents()
        assert chunks == []

    def test_small_chunk_size(self, tmp_kb):
        from src.voxops.rag.document_loader import DocumentLoader

        loader = DocumentLoader(knowledge_dir=tmp_kb, chunk_size=60, chunk_overlap=10)
        chunks = loader.load_documents()
        # With small chunk size we should get more chunks
        assert len(chunks) >= 4, "Small chunk size should produce more chunks"

    def test_chunk_text_not_exceed_size_greatly(self, tmp_kb):
        from src.voxops.rag.document_loader import DocumentLoader

        chunk_size = 100
        loader = DocumentLoader(knowledge_dir=tmp_kb, chunk_size=chunk_size, chunk_overlap=20)
        chunks = loader.load_documents()
        for c in chunks:
            # Allow some tolerance for overlap prepending
            assert len(c.text) <= chunk_size + 100, (
                f"Chunk too large: {len(c.text)} chars (limit ~{chunk_size})"
            )


# ======================================================================
# 2. Embedding Model Tests
# ======================================================================

class TestEmbeddingModel:
    """Tests for embedding_model.py"""

    def test_embed_text_returns_list_of_floats(self):
        from src.voxops.rag.embedding_model import EmbeddingModel

        model = EmbeddingModel()
        vec = model.embed_text("Hello, world!")
        assert isinstance(vec, list)
        assert len(vec) > 0
        assert all(isinstance(v, float) for v in vec)

    def test_embedding_dimension(self):
        from src.voxops.rag.embedding_model import EmbeddingModel

        model = EmbeddingModel()
        assert model.dimension == 384  # all-MiniLM-L6-v2 → 384

    def test_embed_documents_batch(self):
        from src.voxops.rag.embedding_model import EmbeddingModel

        model = EmbeddingModel()
        texts = ["Track my order", "Delivery is delayed", "Where is my package?"]
        vecs = model.embed_documents(texts)
        assert len(vecs) == 3
        assert all(len(v) == 384 for v in vecs)

    def test_embed_documents_empty(self):
        from src.voxops.rag.embedding_model import EmbeddingModel

        model = EmbeddingModel()
        vecs = model.embed_documents([])
        assert vecs == []

    def test_singleton(self):
        from src.voxops.rag.embedding_model import EmbeddingModel

        a = EmbeddingModel.get_instance()
        b = EmbeddingModel.get_instance()
        assert a is b

    def test_cosine_similarity_identical(self):
        from src.voxops.rag.embedding_model import EmbeddingModel

        model = EmbeddingModel()
        vec = model.embed_text("test sentence")
        sim = model.cosine_similarity(vec, vec)
        assert abs(sim - 1.0) < 1e-5

    def test_cosine_similarity_different(self):
        from src.voxops.rag.embedding_model import EmbeddingModel

        model = EmbeddingModel()
        v1 = model.embed_text("I love pizza")
        v2 = model.embed_text("Quantum mechanics is fascinating")
        sim = model.cosine_similarity(v1, v2)
        assert sim < 0.8, "Unrelated sentences should have lower similarity"

    def test_similar_sentences_high_similarity(self):
        from src.voxops.rag.embedding_model import EmbeddingModel

        model = EmbeddingModel()
        v1 = model.embed_text("Where is my shipment?")
        v2 = model.embed_text("Track my package location")
        sim = model.cosine_similarity(v1, v2)
        assert sim > 0.4, f"Similar sentences should have higher similarity, got {sim}"


# ======================================================================
# 3. Vector Store Tests
# ======================================================================

class TestVectorStore:
    """Tests for vector_store.py"""

    def test_add_and_count(self, tmp_kb):
        from src.voxops.rag.document_loader import DocumentLoader
        from src.voxops.rag.vector_store import VectorStore

        loader = DocumentLoader(knowledge_dir=tmp_kb)
        chunks = loader.load_documents()

        store = VectorStore(ephemeral=True, collection_name="test_add_count")
        added = store.add_chunks(chunks)
        assert added == len(chunks)
        assert store.count() == len(chunks)

    def test_query_returns_results(self, tmp_kb):
        from src.voxops.rag.document_loader import DocumentLoader
        from src.voxops.rag.vector_store import VectorStore

        loader = DocumentLoader(knowledge_dir=tmp_kb)
        chunks = loader.load_documents()

        store = VectorStore(ephemeral=True, collection_name="test_query_results")
        store.add_chunks(chunks)

        results = store.query("How do I track my order?", top_k=3)
        assert len(results) > 0
        assert results[0].text  # should have text
        assert results[0].source  # should have source

    def test_query_relevance(self, tmp_kb):
        from src.voxops.rag.document_loader import DocumentLoader
        from src.voxops.rag.vector_store import VectorStore

        loader = DocumentLoader(knowledge_dir=tmp_kb)
        chunks = loader.load_documents()

        store = VectorStore(ephemeral=True, collection_name="test_relevance")
        store.add_chunks(chunks)

        results = store.query("return policy refund", top_k=5)
        assert len(results) > 0
        all_text = " ".join(r.text.lower() for r in results)
        assert "return" in all_text or "refund" in all_text, (
            f"Expected return/refund in results, got: {all_text[:300]}"
        )

    def test_delete_by_source(self, tmp_kb):
        from src.voxops.rag.document_loader import DocumentLoader
        from src.voxops.rag.vector_store import VectorStore

        loader = DocumentLoader(knowledge_dir=tmp_kb)
        chunks = loader.load_documents()

        store = VectorStore(ephemeral=True, collection_name="test_delete_src")
        store.add_chunks(chunks)
        initial = store.count()

        store.delete_by_source("faq.txt")
        assert store.count() < initial

    def test_clear(self, tmp_kb):
        from src.voxops.rag.document_loader import DocumentLoader
        from src.voxops.rag.vector_store import VectorStore

        loader = DocumentLoader(knowledge_dir=tmp_kb)
        chunks = loader.load_documents()

        store = VectorStore(ephemeral=True, collection_name="test_clear")
        store.add_chunks(chunks)
        assert store.count() > 0

        store.clear()
        assert store.count() == 0

    def test_list_sources(self, tmp_kb):
        from src.voxops.rag.document_loader import DocumentLoader
        from src.voxops.rag.vector_store import VectorStore

        loader = DocumentLoader(knowledge_dir=tmp_kb)
        chunks = loader.load_documents()

        store = VectorStore(ephemeral=True, collection_name="test_list_src")
        store.add_chunks(chunks)

        srcs = store.list_sources()
        assert "policies.txt" in srcs
        assert "faq.txt" in srcs

    def test_query_with_source_filter(self, tmp_kb):
        from src.voxops.rag.document_loader import DocumentLoader
        from src.voxops.rag.vector_store import VectorStore

        loader = DocumentLoader(knowledge_dir=tmp_kb)
        chunks = loader.load_documents()

        store = VectorStore(ephemeral=True, collection_name="test_filter")
        store.add_chunks(chunks)

        results = store.query("delivery", top_k=10, where={"source": "policies.txt"})
        for r in results:
            assert r.source == "policies.txt"

    def test_upsert_idempotent(self, tmp_kb):
        from src.voxops.rag.document_loader import DocumentLoader
        from src.voxops.rag.vector_store import VectorStore

        loader = DocumentLoader(knowledge_dir=tmp_kb)
        chunks = loader.load_documents()

        store = VectorStore(ephemeral=True, collection_name="test_upsert")
        store.add_chunks(chunks)
        count1 = store.count()

        # Upsert again — count should stay same (same IDs)
        store.add_chunks(chunks)
        count2 = store.count()
        assert count1 == count2, "Upsert should not duplicate documents"


# ======================================================================
# 4. Retriever Tests
# ======================================================================

class TestRetriever:
    """Tests for retriever.py"""

    def test_ingest_and_retrieve(self, tmp_kb):
        from src.voxops.rag.document_loader import DocumentLoader
        from src.voxops.rag.vector_store import VectorStore
        from src.voxops.rag.embedding_model import EmbeddingModel
        from src.voxops.rag.retriever import Retriever

        store = VectorStore(ephemeral=True, collection_name="test_ingest_retrieve")
        loader = DocumentLoader(knowledge_dir=tmp_kb)
        retriever = Retriever(vector_store=store, document_loader=loader)

        count = retriever.ingest_knowledge_base()
        assert count > 0

        result = retriever.retrieve("How do I track my order?")
        assert result.query == "How do I track my order?"
        assert len(result.passages) > 0
        assert result.context_text  # non-empty
        assert result.num_sources > 0

    def test_retrieve_context_string(self, tmp_kb):
        from src.voxops.rag.document_loader import DocumentLoader
        from src.voxops.rag.vector_store import VectorStore
        from src.voxops.rag.retriever import Retriever

        store = VectorStore(ephemeral=True, collection_name="test_ctx_str")
        loader = DocumentLoader(knowledge_dir=tmp_kb)
        retriever = Retriever(vector_store=store, document_loader=loader)
        retriever.ingest_knowledge_base()

        ctx = retriever.retrieve_context_string("delivery timeframes")
        assert isinstance(ctx, str)
        assert len(ctx) > 0

    def test_ingest_skips_if_populated(self, tmp_kb):
        from src.voxops.rag.document_loader import DocumentLoader
        from src.voxops.rag.vector_store import VectorStore
        from src.voxops.rag.retriever import Retriever

        store = VectorStore(ephemeral=True, collection_name="test_skip")
        loader = DocumentLoader(knowledge_dir=tmp_kb)
        retriever = Retriever(vector_store=store, document_loader=loader)

        c1 = retriever.ingest_knowledge_base()
        c2 = retriever.ingest_knowledge_base()
        assert c2 == c1, "Second ingest should skip and return existing count"

    def test_ingest_force_reloads(self, tmp_kb):
        from src.voxops.rag.document_loader import DocumentLoader
        from src.voxops.rag.vector_store import VectorStore
        from src.voxops.rag.retriever import Retriever

        store = VectorStore(ephemeral=True, collection_name="test_force")
        loader = DocumentLoader(knowledge_dir=tmp_kb)
        retriever = Retriever(vector_store=store, document_loader=loader)

        retriever.ingest_knowledge_base()
        c2 = retriever.ingest_knowledge_base(force=True)
        assert c2 > 0

    def test_ingest_file(self, tmp_kb):
        from src.voxops.rag.document_loader import DocumentLoader
        from src.voxops.rag.vector_store import VectorStore
        from src.voxops.rag.retriever import Retriever

        store = VectorStore(ephemeral=True, collection_name="test_ingest_file")
        loader = DocumentLoader(knowledge_dir=tmp_kb)
        retriever = Retriever(vector_store=store, document_loader=loader)

        added = retriever.ingest_file("faq.txt")
        assert added > 0
        srcs = retriever.list_indexed_sources()
        assert "faq.txt" in srcs

    def test_store_count(self, tmp_kb):
        from src.voxops.rag.document_loader import DocumentLoader
        from src.voxops.rag.vector_store import VectorStore
        from src.voxops.rag.retriever import Retriever

        store = VectorStore(ephemeral=True, collection_name="test_store_count")
        loader = DocumentLoader(knowledge_dir=tmp_kb)
        retriever = Retriever(vector_store=store, document_loader=loader)

        assert retriever.store_count() == 0
        retriever.ingest_knowledge_base()
        assert retriever.store_count() > 0

    def test_source_filter_in_retrieval(self, tmp_kb):
        from src.voxops.rag.document_loader import DocumentLoader
        from src.voxops.rag.vector_store import VectorStore
        from src.voxops.rag.retriever import Retriever

        store = VectorStore(ephemeral=True, collection_name="test_src_filter")
        loader = DocumentLoader(knowledge_dir=tmp_kb)
        retriever = Retriever(vector_store=store, document_loader=loader)
        retriever.ingest_knowledge_base()

        result = retriever.retrieve("delivery", source_filter="policies.txt")
        for p in result.passages:
            assert p.source == "policies.txt"

    def test_max_context_chars_respected(self, tmp_kb):
        from src.voxops.rag.document_loader import DocumentLoader
        from src.voxops.rag.vector_store import VectorStore
        from src.voxops.rag.retriever import Retriever

        store = VectorStore(ephemeral=True, collection_name="test_max_ctx")
        loader = DocumentLoader(knowledge_dir=tmp_kb)
        retriever = Retriever(
            vector_store=store, document_loader=loader, max_context_chars=100
        )
        retriever.ingest_knowledge_base()

        result = retriever.retrieve("delivery")
        # The context text may slightly exceed due to separators, but should be bounded
        assert len(result.context_text) <= 300, (
            f"Context too long: {len(result.context_text)} chars"
        )


# ======================================================================
# 5. Integration — Real Knowledge Base
# ======================================================================

class TestRealKnowledgeBase:
    """Integration tests using the actual knowledge-base files."""

    def test_load_real_knowledge_base(self):
        from src.voxops.rag.document_loader import DocumentLoader
        from configs.settings import settings

        loader = DocumentLoader()
        chunks = loader.load_documents()
        assert len(chunks) > 0, "Real knowledge base should produce chunks"

        sources = {c.source for c in chunks}
        assert "company_policies.txt" in sources
        assert "faq.txt" in sources

    def test_full_pipeline_real_kb(self):
        from src.voxops.rag.vector_store import VectorStore
        from src.voxops.rag.document_loader import DocumentLoader
        from src.voxops.rag.retriever import Retriever

        store = VectorStore(ephemeral=True, collection_name="test_real_kb")
        retriever = Retriever(vector_store=store)
        count = retriever.ingest_knowledge_base()
        assert count > 0

        # Test a few queries against the real knowledge base
        queries = [
            ("How do I track my shipment?", ["track", "tracking", "order", "portal", "voice"]),
            ("What is the return policy?", ["return", "refund", "30", "missing", "damaged"]),
            ("What happens if my package is delayed?", ["delay", "traffic", "weather", "revised", "ETA"]),
            ("How do I file a complaint?", ["escalat", "agent", "ticket", "complaint", "speak"]),
        ]

        for query, expected_keywords in queries:
            result = retriever.retrieve(query)
            context_lower = result.context_text.lower()
            found = any(kw.lower() in context_lower for kw in expected_keywords)
            assert found, (
                f"Query '{query}' should return context containing one of {expected_keywords}, "
                f"got: {result.context_text[:200]}"
            )
