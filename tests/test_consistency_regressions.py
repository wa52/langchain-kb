from unittest.mock import MagicMock, patch

import pytest
from langchain_core.documents import Document


def test_graph_rebuild_reads_current_vector_collection():
    from src.ingestion.pipeline import _rebuild_graph_from_store

    collection = MagicMock()
    collection.count.return_value = 2
    collection.get.return_value = {
        "documents": ["first", "second"],
        "metadatas": [{"source": "a.md"}, {"source": "b.md"}],
    }
    store = MagicMock()
    store._collection = collection
    graph = MagicMock()

    with (
        patch("src.ingestion.pipeline.get_vector_store", return_value=store),
        patch("src.graph_store.graph.KnowledgeGraph", return_value=graph),
        patch("src.graph_store.retriever.set_graph") as set_graph,
        patch("config.ENABLE_GRAPH_LLM_EXTRACTION", False),
    ):
        result = _rebuild_graph_from_store(echo_fn=lambda *args, **kwargs: None)

    chunks = graph.build_from_chunks.call_args.args[0]
    assert [chunk.page_content for chunk in chunks] == ["first", "second"]
    assert [chunk.metadata["source"] for chunk in chunks] == ["a.md", "b.md"]
    graph.save.assert_called_once()
    set_graph.assert_called_once_with(graph)
    assert result is graph


def test_single_file_parse_failure_preserves_existing_index(tmp_path):
    from src.ingestion.pipeline import run_single_file_update

    source = tmp_path / "broken.md"
    source.write_text("content", encoding="utf-8")
    with (
        patch("src.ingestion.pipeline.load_path", return_value=[]),
        patch("src.ingestion.pipeline.delete_by_source") as delete,
    ):
        count = run_single_file_update(str(source), echo_fn=lambda *args, **kwargs: None)

    assert count == 0
    delete.assert_not_called()


def test_replace_rolls_back_previous_documents_when_write_fails():
    from src.ingestion.pipeline import _replace_documents

    previous = Document(page_content="old", metadata={"source": "a.md"})
    replacement = Document(page_content="new", metadata={"source": "a.md"})
    with (
        patch("src.ingestion.pipeline._stored_documents", return_value=[previous]),
        patch("src.ingestion.pipeline.delete_by_source") as delete,
        patch("src.ingestion.pipeline.invalidate_bm25"),
        patch("src.ingestion.pipeline.add_documents_with_progress",
              side_effect=[RuntimeError("write failed"), None]) as add,
        patch("src.ingestion.pipeline.rebuild_bm25") as rebuild,
        patch("src.ingestion.pipeline.get_vector_store", return_value=MagicMock()),
    ):
        with pytest.raises(RuntimeError, match="write failed"):
            _replace_documents({"a.md"}, [replacement], echo_fn=lambda *a, **k: None)

    assert delete.call_count == 2
    assert add.call_args_list[1].args[0] == [previous]
    rebuild.assert_called_once()
