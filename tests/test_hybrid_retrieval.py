"""F1 regression: hybrid (vector + BM25) retrieval must actually take effect.

Previously `src/vector_store/service.py` did
`from src.retrieval.retriever import ... _bm25_retriever`, which bound None
at import time. Every production retrieval path (agent tools, CLI search,
project workflow, solution generator) goes through `VectorStoreService`, so
the rebuilt BM25 index was never used and `ENABLE_HYBRID_SEARCH` was a no-op.
"""

from unittest.mock import MagicMock, patch

from langchain_core.retrievers import BaseRetriever

import src.retrieval.retriever as retriever_mod
from src.vector_store.service import VectorStoreService


def _retriever_mock():
    return MagicMock(spec=BaseRetriever)


def test_hybrid_active_after_bm25_rebuild():
    """Simulates the real ordering: service imported while the BM25 global is
    still None, then rebuild_bm25() sets it later. get_retriever must see it."""
    fake_bm25 = _retriever_mock()
    fake_vector = _retriever_mock()
    fake_vs = MagicMock()
    fake_vs.as_retriever.return_value = fake_vector

    with (
        patch("src.vector_store.service.ENABLE_HYBRID_SEARCH", True),
        patch("src.vector_store.service.get_vector_store", return_value=fake_vs),
        patch("src.vector_store.service.get_embedding_model", return_value=MagicMock()),
    ):
        retriever_mod._bm25_retriever = None
        before = VectorStoreService().get_retriever(k=5)
        assert not hasattr(before, "retrievers"), "no BM25 yet -> plain vector retriever"

        retriever_mod._bm25_retriever = fake_bm25
        after = VectorStoreService().get_retriever(k=5)
        assert getattr(after, "retrievers", None) is not None, (
            "hybrid retrieval must be active once BM25 is rebuilt"
        )
        assert fake_vector in after.retrievers
        assert fake_bm25 in after.retrievers


def test_hybrid_respects_disabled_flag():
    fake_bm25 = _retriever_mock()
    fake_vector = _retriever_mock()
    fake_vs = MagicMock()
    fake_vs.as_retriever.return_value = fake_vector

    with (
        patch("src.vector_store.service.ENABLE_HYBRID_SEARCH", False),
        patch("src.vector_store.service.get_vector_store", return_value=fake_vs),
        patch("src.vector_store.service.get_embedding_model", return_value=MagicMock()),
    ):
        retriever_mod._bm25_retriever = fake_bm25
        r = VectorStoreService().get_retriever(k=5)
        assert not hasattr(r, "retrievers"), "hybrid disabled -> plain vector retriever"


def test_bm25_tokenize_splits_chinese():
    """F4: the BM25 preprocess function must segment Chinese instead of
    treating a whole chunk as one whitespace token."""
    tokens = retriever_mod._bm25_tokenize("边缘检测是工业视觉的核心算法")
    assert len(tokens) >= 3, f"expected several Chinese tokens, got {tokens}"
    assert all(isinstance(t, str) and t.strip() for t in tokens)
