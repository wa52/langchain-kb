"""BM25 in-memory index invalidation regression tests.

rebuild_bm25 must skip the in-memory index only when the collection count is
unchanged; after a data change (indexing / experience sync inside a running
server) it has to force a full rebuild so hybrid retrieval never misses the
new chunks.
"""

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def cleanup_bm25_global():
    from src.retrieval import retriever as retriever_mod
    saved = retriever_mod._bm25_retriever
    saved_invalidated = retriever_mod._bm25_invalidated
    retriever_mod._bm25_retriever = None
    retriever_mod._bm25_invalidated = False
    yield
    retriever_mod._bm25_retriever = saved
    retriever_mod._bm25_invalidated = saved_invalidated


def _make_store():
    mock_store = MagicMock()
    mock_store._collection.get.side_effect = [
        {"documents": ["text1", "text2"], "metadatas": [{"source": "a.md"}, {"source": "b.md"}]},
        {"documents": [], "metadatas": []},
    ]
    return mock_store


class TestBm25RebuildOnDataChange:
    @patch("src.retrieval.retriever._save_bm25_to_disk")
    @patch("src.retrieval.retriever._load_bm25_from_disk", return_value=False)
    def test_in_memory_index_skipped_when_count_matches(self, _load, _save):
        from src.retrieval import retriever as retriever_mod
        from src.status import snapshot_status
        fake = MagicMock()
        fake.docs = ["a"] * 2
        retriever_mod._bm25_retriever = fake
        store = _make_store()
        store._collection.count.return_value = 2
        retriever_mod.rebuild_bm25(store, echo_fn=lambda _: None)
        assert "已在内存" in snapshot_status()["bm25"]["detail"]

    @patch("src.retrieval.retriever._save_bm25_to_disk")
    @patch("src.retrieval.retriever._load_bm25_from_disk", return_value=False)
    def test_stale_in_memory_index_is_rebuilt(self, _load, _save):
        from src.retrieval import retriever as retriever_mod
        from src.status import snapshot_status
        fake = MagicMock()
        fake.docs = ["a"] * 3
        retriever_mod._bm25_retriever = fake
        store = _make_store()
        store._collection.count.return_value = 2
        retriever_mod.rebuild_bm25(store, echo_fn=lambda _: None)
        assert "全量重建" in snapshot_status()["bm25"]["detail"]
        # the stale in-memory index was replaced
        assert retriever_mod._bm25_retriever is not fake

    @patch("src.retrieval.retriever._save_bm25_to_disk")
    @patch("src.retrieval.retriever._load_bm25_from_disk", return_value=False)
    def test_explicit_invalidation_rebuilds_when_count_is_unchanged(self, _load, _save):
        from src.retrieval import retriever as retriever_mod
        fake = MagicMock()
        fake.docs = ["old1", "old2"]
        retriever_mod._bm25_retriever = fake
        store = _make_store()
        store._collection.count.return_value = 2

        retriever_mod.invalidate_bm25()
        retriever_mod.rebuild_bm25(store, echo_fn=lambda _: None)

        assert retriever_mod._bm25_retriever is not fake
        assert [doc.page_content for doc in retriever_mod._bm25_retriever.docs] == ["text1", "text2"]

    def test_invalidation_removes_persisted_cache(self, tmp_path):
        from src.retrieval import retriever as retriever_mod

        cache = tmp_path / "bm25_index.pkl"
        cache.write_bytes(b"stale")
        with patch.object(retriever_mod, "_BM25_PERSIST_PATH", cache):
            retriever_mod.invalidate_bm25()
        assert not cache.exists()
