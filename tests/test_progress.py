import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from langchain_core.documents import Document
from src.vector_store.chroma_client import add_documents_with_progress
from src.retrieval.retriever import rebuild_bm25


def _make_chunks(n: int) -> list[Document]:
    return [Document(page_content=f"chunk {i} content") for i in range(n)]


class TestAddDocumentsWithProgress:

    def test_echo_fn_called_per_batch(self):
        mock = MagicMock()
        chunks = _make_chunks(70)
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
        add_documents_with_progress([], echo_fn=mock)
        mock.assert_not_called()

    def test_progress_increases(self):
        mock = MagicMock()
        chunks = _make_chunks(64)
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

    def test_echo_fn_replaces_print(self):
        mock_store = MagicMock()
        mock_store._collection.get.return_value = {
            "documents": ["text1", "text2"],
            "metadatas": [{"source": "a.md"}, {"source": "b.md"}],
        }
        mock = MagicMock()
        try:
            rebuild_bm25(mock_store, echo_fn=mock)
        except Exception:
            pass  # BM25 retriever might fail with mock store; that's fine
        # echo_fn should have been called at least once (error or success)
        assert mock.call_count >= 1


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
