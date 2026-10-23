from contextlib import nullcontext
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


def test_tracked_reindex_preserves_nested_source_key(tmp_path):
    from src.ingestion.pipeline import run_tracked_file_update

    root = tmp_path / "external"
    source = root / "manuals" / "example.md"
    source.parent.mkdir(parents=True)
    source.write_text("new content", encoding="utf-8")
    store = MagicMock()
    store._collection.get.return_value = {"documents": [], "metadatas": []}
    with (
        patch("src.ingestion.pipeline._cross_process_index_lock", return_value=nullcontext()),
        patch("src.ingestion.pipeline.get_embedding_model"),
        patch("src.ingestion.pipeline.get_vector_store", return_value=store),
        patch("src.ingestion.pipeline.add_documents_with_progress") as add,
        patch("src.ingestion.pipeline.delete_by_source") as delete,
        patch("src.ingestion.pipeline.rebuild_bm25"),
        patch("src.ingestion.pipeline.update_tracker") as update_tracker,
        patch("config.ENABLE_GRAPH", False),
    ):
        count = run_tracked_file_update(str(source), str(root), "external",
                                        echo_fn=lambda *args, **kwargs: None)

    assert count > 0
    assert {call.args[0] for call in delete.call_args_list} == {
        "manuals/example.md", str(source.relative_to(root)),
    }
    assert all(chunk.metadata["source"] == "manuals/example.md"
               for chunk in add.call_args.args[0])
    update_tracker.assert_called_once_with("external", root.resolve(), [str(source.resolve())])


def test_tracked_reindex_parse_failure_preserves_existing_index(tmp_path):
    from src.ingestion.pipeline import run_tracked_file_update

    source = tmp_path / "broken.md"
    source.write_text("content", encoding="utf-8")
    with (
        patch("src.ingestion.pipeline._cross_process_index_lock", return_value=nullcontext()),
        patch("src.ingestion.pipeline.load_files", return_value=[]),
        patch("src.ingestion.pipeline.delete_by_source") as delete,
    ):
        with pytest.raises(ValueError, match="原索引保持不变"):
            run_tracked_file_update(str(source), str(tmp_path), "external",
                                    echo_fn=lambda *args, **kwargs: None)
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


def test_tracked_remove_targets_one_nested_source_and_retains_disk_files(tmp_path, monkeypatch):
    from src.ingestion.pipeline import run_tracked_file_remove
    from src.ingestion import tracker

    monkeypatch.setattr(tracker, "TRACKER_FILE", str(tmp_path / "tracker.json"))
    root = tmp_path / "external"
    first = root / "manuals" / "same.md"
    second = root / "other" / "same.md"
    for path in (first, second):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(str(path), encoding="utf-8")
    tracker.update_tracker("external", root, [str(first), str(second)])
    store = MagicMock()
    store._collection.get.return_value = {"documents": [], "metadatas": []}
    with (
        patch("src.ingestion.pipeline._cross_process_index_lock", return_value=nullcontext()),
        patch("src.ingestion.pipeline.get_vector_store", return_value=store),
        patch("src.ingestion.pipeline.delete_by_source") as delete,
        patch("src.ingestion.pipeline.add_documents_with_progress"),
        patch("src.ingestion.pipeline.rebuild_bm25"),
        patch("config.ENABLE_GRAPH", False),
    ):
        result = run_tracked_file_remove("external", "manuals/same.md",
                                         echo_fn=lambda *a, **k: None)

    assert result == {"removed": "manuals/same.md", "source_type": "external", "file_retained": True}
    assert {call.args[0] for call in delete.call_args_list} == {
        "manuals/same.md", "manuals\\same.md",
    }
    assert [item["file_key"] for item in tracker.list_all_files()] == ["other\\same.md"]
    assert first.exists() and second.exists()


def test_tracked_remove_restores_index_on_rebuild_failure(tmp_path, monkeypatch):
    from src.ingestion.pipeline import run_tracked_file_remove
    from src.ingestion import tracker

    monkeypatch.setattr(tracker, "TRACKER_FILE", str(tmp_path / "tracker.json"))
    root = tmp_path / "external"
    root.mkdir()
    source = root / "same.md"
    source.write_text("old", encoding="utf-8")
    tracker.update_tracker("external", root, [str(source)])
    store = MagicMock()
    store._collection.get.return_value = {
        "documents": ["old"], "metadatas": [{"source": "same.md"}],
    }
    with (
        patch("src.ingestion.pipeline._cross_process_index_lock", return_value=nullcontext()),
        patch("src.ingestion.pipeline.get_vector_store", return_value=store),
        patch("src.ingestion.pipeline.delete_by_source"),
        patch("src.ingestion.pipeline.add_documents_with_progress") as add,
        patch("src.ingestion.pipeline.rebuild_bm25", side_effect=[RuntimeError("rebuild failed"), None]),
        patch("config.ENABLE_GRAPH", False),
    ):
        with pytest.raises(RuntimeError, match="rebuild failed"):
            run_tracked_file_remove("external", "same.md", echo_fn=lambda *a, **k: None)

    assert [item["file_key"] for item in tracker.list_all_files()] == ["same.md"]
    assert source.exists()
    assert any(call.args[0] and call.args[0][0].page_content == "old" for call in add.call_args_list)
