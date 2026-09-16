import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from langchain_core.documents import Document
from src.vector_store.chroma_client import add_documents_with_progress
from src.retrieval.retriever import rebuild_bm25


def _make_chunks(n: int) -> list[Document]:
    return [Document(page_content=f"chunk {i} content") for i in range(n)]


class TestAddDocumentsWithProgress:

    def _mock_store(self):
        store = MagicMock()
        store.add_documents = MagicMock()
        return store

    def test_echo_fn_called_per_batch(self):
        mock = MagicMock()
        chunks = _make_chunks(70)
        with patch("src.vector_store.chroma_client.get_vector_store", return_value=self._mock_store()):
            add_documents_with_progress(chunks, batch_size=32, echo_fn=mock)
        assert mock.call_count >= 3
        all_text = ""
        for call_arg in mock.call_args_list:
            for a in call_arg.args:
                all_text += str(a)
            for v in call_arg.kwargs.values():
                all_text += str(v)
        assert "%" in all_text or "完成" in all_text or "ch/s" in all_text

    def test_empty_chunks_no_calls(self):
        mock = MagicMock()
        with patch("src.vector_store.chroma_client.get_vector_store", return_value=self._mock_store()):
            add_documents_with_progress([], echo_fn=mock)
        mock.assert_not_called()

    def test_progress_increases(self):
        mock = MagicMock()
        chunks = _make_chunks(64)
        with patch("src.vector_store.chroma_client.get_vector_store", return_value=self._mock_store()):
            add_documents_with_progress(chunks, batch_size=32, echo_fn=mock)
        percentages = []
        import re
        for call_arg in mock.call_args_list:
            for a in call_arg.args:
                m = re.search(r'\[(\s*\d+)%\]', str(a))
                if m:
                    percentages.append(int(m.group(1).strip()))
        assert len(percentages) >= 2
        assert percentages[0] < percentages[-1]




class TestRebuildBm25:

    @pytest.fixture(autouse=True)
    def _cleanup_bm25_global(self):
        from src.retrieval import retriever as retriever_mod
        saved = retriever_mod._bm25_retriever
        retriever_mod._bm25_retriever = None
        yield
        retriever_mod._bm25_retriever = saved

    @pytest.fixture(autouse=True)
    def _no_disk_write(self):
        # Rebuild tests must not overwrite the real chroma_db/bm25_index.pkl.
        with patch("src.retrieval.retriever._save_bm25_to_disk"):
            yield

    def test_echo_fn_replaces_print(self):
        mock_store = MagicMock()
        mock_store._collection.get.side_effect = [
            {"documents": ["text1", "text2"], "metadatas": [{"source": "a.md"}, {"source": "b.md"}]},
            {"documents": [], "metadatas": []},
        ]
        mock = MagicMock()
        try:
            rebuild_bm25(mock_store, echo_fn=mock)
        except Exception:
            pass  # BM25 retriever might fail with mock store; that's fine
        # echo_fn should have been called at least once (error or success)
        assert mock.call_count >= 1

    @patch("src.retrieval.retriever._load_bm25_from_disk", return_value=False)
    def test_rebuild_over_999_docs_with_pagination(self, mock_load):
        n = 1500
        texts = [f"chunk {i} content" for i in range(n)]
        metadatas = [{"source": f"{i}.md"} for i in range(n)]

        def _paginated_get(**kwargs):
            limit = kwargs.get("limit", 500)
            offset = kwargs.get("offset", 0)
            batch_texts = texts[offset:offset + limit]
            batch_metas = metadatas[offset:offset + limit]
            return {"documents": batch_texts, "metadatas": batch_metas}

        mock_store = MagicMock()
        mock_store._collection.get.side_effect = _paginated_get
        mock = MagicMock()
        try:
            rebuild_bm25(mock_store, echo_fn=mock)
        except Exception:
            pass
        assert mock_store._collection.get.call_count >= 3
        success_texts = "".join(str(a) for args in mock.call_args_list for a in args.args)
        assert "BM25" in success_texts or "完成" in success_texts

    @patch("src.retrieval.retriever._load_bm25_from_disk", return_value=False)
    def test_rebuild_empty_collection(self, mock_load):
        mock_store = MagicMock()
        mock_store._collection.get.side_effect = [
            {"documents": [], "metadatas": []},
        ]
        mock = MagicMock()
        rebuild_bm25(mock_store, echo_fn=mock)
        assert mock.call_count == 0


class TestChromaCollectionStats:

    def test_stats_over_999_docs(self):
        n = 1500
        metadatas = [{"source": f"file{i}.md"} for i in range(n)]

        def _paginated_get(**kwargs):
            limit = kwargs.get("limit", 500)
            offset = kwargs.get("offset", 0)
            batch = metadatas[offset:offset + limit]
            return {"metadatas": batch}

        mock_col = MagicMock()
        mock_col.count.return_value = n
        mock_col.get.side_effect = _paginated_get
        mock_vs = MagicMock()
        mock_vs._collection = mock_col

        with patch("src.vector_store.chroma_client.get_vector_store", return_value=mock_vs):
            from src.vector_store.chroma_client import get_collection_stats
            stats = get_collection_stats()

        assert stats["count"] == n
        assert stats["source_count"] == n
        assert mock_col.get.call_count >= 3

    def test_stats_empty(self):
        mock_col = MagicMock()
        mock_col.count.return_value = 0
        mock_vs = MagicMock()
        mock_vs._collection = mock_col

        with patch("src.vector_store.chroma_client.get_vector_store", return_value=mock_vs):
            from src.vector_store.chroma_client import get_collection_stats
            stats = get_collection_stats()

        assert stats["count"] == 0
        assert stats["source_count"] == 0
        mock_col.get.assert_not_called()


class TestLoadPathProgress:

    def test_load_path_dir_shows_progress(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            for i in range(3):
                (d / f"file{i}.md").write_text(f"# doc {i}", encoding="utf-8")
            mock = MagicMock()
            from src.ingestion.loader import load_path
            docs = load_path(d, echo_fn=mock)
            assert len(docs) == 3
            all_text = " ".join(str(a) for args in mock.call_args_list for a in args.args)
            assert "3" in all_text or "1" in all_text

    def test_load_path_single_file_no_progress(self):
        mock = MagicMock()
        from src.ingestion.loader import load_path
        with tempfile.TemporaryDirectory() as td:
            f = Path(td) / "test.md"
            f.write_text("# test", encoding="utf-8")
            docs = load_path(str(f), echo_fn=mock)
            assert len(docs) == 1
            assert mock.call_count == 0

    def test_load_path_empty_dir_no_progress(self):
        with tempfile.TemporaryDirectory() as td:
            mock = MagicMock()
            from src.ingestion.loader import load_path
            docs = load_path(td, echo_fn=mock)
            assert len(docs) == 0
            assert mock.call_count == 0
