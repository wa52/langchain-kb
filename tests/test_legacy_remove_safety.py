"""The basename-only compatibility entry must fail closed on ambiguous sources."""

from contextlib import nullcontext
from unittest.mock import MagicMock, patch

import pytest


def _track(monkeypatch, tmp_path, entries):
    from src.ingestion import tracker

    monkeypatch.setattr(tracker, "TRACKER_FILE", str(tmp_path / "tracker.json"))
    root = tmp_path / "external"
    root.mkdir()
    for key in entries:
        path = root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(key, encoding="utf-8")
    tracker.update_tracker("external", root, [str(root / key) for key in entries])
    return root


def test_legacy_remove_rejects_duplicate_basename_without_touching_index(tmp_path, monkeypatch):
    from src.ingestion.pipeline import run_remove

    root = _track(monkeypatch, tmp_path, ["manuals/same.md", "examples/same.md"])
    with (
        patch("src.ingestion.pipeline._cross_process_index_lock", return_value=nullcontext()),
        patch("src.ingestion.pipeline.delete_by_source") as delete,
    ):
        with pytest.raises(ValueError, match="无法唯一定位"):
            run_remove("same.md", str(root), echo_fn=lambda *a, **k: None)
    delete.assert_not_called()
    assert (root / "manuals/same.md").exists()
    assert (root / "examples/same.md").exists()


def test_legacy_remove_rejects_directory_without_touching_index(tmp_path, monkeypatch):
    from src.ingestion.pipeline import run_remove

    root = _track(monkeypatch, tmp_path, ["same.md"])
    (root / "same.md").unlink()
    (root / "same.md").mkdir()
    with (
        patch("src.ingestion.pipeline._cross_process_index_lock", return_value=nullcontext()),
        patch("src.ingestion.pipeline.delete_by_source") as delete,
    ):
        with pytest.raises(ValueError, match="普通文件"):
            run_remove("same.md", str(root), echo_fn=lambda *a, **k: None)
    delete.assert_not_called()
    assert (root / "same.md").is_dir()


def test_legacy_remove_unique_flat_file_updates_index_then_deletes_disk(tmp_path, monkeypatch):
    from src.ingestion.pipeline import run_remove
    from src.ingestion import tracker

    root = _track(monkeypatch, tmp_path, ["same.md"])
    store = MagicMock()
    store._collection.get.return_value = {"documents": [], "metadatas": []}
    with (
        patch("src.ingestion.pipeline._cross_process_index_lock", return_value=nullcontext()),
        patch("src.ingestion.pipeline.get_vector_store", return_value=store),
        patch("src.ingestion.pipeline.delete_by_source") as delete,
        patch("src.ingestion.pipeline.rebuild_bm25"),
        patch("config.ENABLE_GRAPH", False),
    ):
        run_remove("same.md", str(root), echo_fn=lambda *a, **k: None)
    delete.assert_called_once_with("same.md")
    assert tracker.list_all_files() == []
    assert not (root / "same.md").exists()


def test_legacy_remove_rebuild_failure_retains_disk_and_tracker(tmp_path, monkeypatch):
    from src.ingestion.pipeline import run_remove
    from src.ingestion import tracker

    root = _track(monkeypatch, tmp_path, ["same.md"])
    store = MagicMock()
    store._collection.get.return_value = {
        "documents": ["old"], "metadatas": [{"source": "same.md"}],
    }
    with (
        patch("src.ingestion.pipeline._cross_process_index_lock", return_value=nullcontext()),
        patch("src.ingestion.pipeline.get_vector_store", return_value=store),
        patch("src.ingestion.pipeline.delete_by_source"),
        patch("src.ingestion.pipeline.add_documents_with_progress") as restore,
        patch("src.ingestion.pipeline.rebuild_bm25",
              side_effect=[RuntimeError("rebuild failed"), None]),
        patch("config.ENABLE_GRAPH", False),
    ):
        with pytest.raises(RuntimeError, match="rebuild failed"):
            run_remove("same.md", str(root), echo_fn=lambda *a, **k: None)
    assert (root / "same.md").exists()
    assert [row["file_key"] for row in tracker.list_all_files()] == ["same.md"]
    assert restore.called
