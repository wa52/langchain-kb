"""Tests for in-place incremental sync of experience-library directories."""

from contextlib import ExitStack
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def isolate_tracker(tmp_path):
    import src.ingestion.tracker as tracker
    original = tracker.TRACKER_FILE
    tracker.TRACKER_FILE = str(tmp_path / "file_tracker.json")
    yield
    tracker.TRACKER_FILE = original


@pytest.fixture
def experience_dir(tmp_path) -> Path:
    d = tmp_path / "experience"
    (d / "patterns").mkdir(parents=True)
    (d / "failure_database").mkdir()
    (d / "patterns" / "llm_batch_parallel_extraction.md").write_text(
        "# LLM 批量并行化\n\n用 ThreadPoolExecutor 并行调用 DeepSeek 提速。", encoding="utf-8"
    )
    (d / "failure_database" / "curl_json.md").write_text(
        "# curl JSON 乱码\n\nPowerShell 传参中文会被破坏。", encoding="utf-8"
    )
    return d


def _enter_pipeline_patches(stack: ExitStack, dirs: list[str]):
    stack.enter_context(patch("config.EXPERIENCE_DIRS", dirs))
    stack.enter_context(patch("src.ingestion.pipeline.get_embedding_model", return_value=MagicMock()))
    stack.enter_context(patch("src.ingestion.pipeline.get_vector_store", return_value=MagicMock()))
    add_docs = stack.enter_context(patch("src.ingestion.pipeline.add_documents_with_progress"))
    stack.enter_context(patch("src.ingestion.pipeline.rebuild_bm25"))
    delete_src = stack.enter_context(patch("src.ingestion.pipeline.delete_by_source"))
    stack.enter_context(patch("src.graph_store.graph.KnowledgeGraph", return_value=MagicMock()))
    stack.enter_context(patch("src.graph_store.retriever.set_graph"))
    return add_docs, delete_src


class TestSyncExperience:
    def test_first_run_indexes_new_files(self, experience_dir, tmp_path):
        from src.ingestion.pipeline import sync_experience
        from src.ingestion.tracker import get_changed_files

        with ExitStack() as stack:
            add_docs, _ = _enter_pipeline_patches(stack, [str(experience_dir)])
            result = sync_experience(echo_fn=lambda *a, **k: None)

        assert result["dirs"] == 1
        assert result["changed"] == 2
        assert result["chunks"] > 0
        assert add_docs.call_count == 1
        added = add_docs.call_args.args[0]
        assert len(added) == result["chunks"]
        # tracker recorded both files -> next run sees no changes
        changed, _ = get_changed_files([(str(experience_dir), "experience")])
        assert changed == []

    def test_no_changes_skips(self, experience_dir, tmp_path):
        from src.ingestion.pipeline import sync_experience

        with ExitStack() as stack:
            add_docs, _ = _enter_pipeline_patches(stack, [str(experience_dir)])
            sync_experience(echo_fn=lambda *a, **k: None)
            add_docs.reset_mock()
            result = sync_experience(echo_fn=lambda *a, **k: None)
        assert result["changed"] == 0
        assert result["chunks"] == 0
        add_docs.assert_not_called()

    def test_modified_file_reindexed_by_full_source(self, experience_dir, tmp_path):
        from src.ingestion.pipeline import sync_experience
        from src.ingestion.tracker import get_changed_files

        with ExitStack() as stack:
            _, delete_src = _enter_pipeline_patches(stack, [str(experience_dir)])
            sync_experience(echo_fn=lambda *a, **k: None)

            # modify one file only
            target = experience_dir / "failure_database" / "curl_json.md"
            target.write_text("# curl JSON 乱码（更新）\n\n新增内容。", encoding="utf-8")
            delete_src.reset_mock()
            result = sync_experience(echo_fn=lambda *a, **k: None)

        assert result["changed"] == 1
        assert result["chunks"] > 0
        # old chunks deleted by full relative source, not basename
        deleted_sources = [c.args[0] for c in delete_src.call_args_list]
        assert str(Path("failure_database") / "curl_json.md") in deleted_sources
        # tracker sees the change as processed
        changed, _ = get_changed_files([(str(experience_dir), "experience")])
        assert changed == []

    def test_unconfigured_returns_zero(self, tmp_path):
        from src.ingestion.pipeline import sync_experience

        with patch("config.EXPERIENCE_DIRS", []):
            result = sync_experience(echo_fn=lambda *a, **k: None)
        assert result["dirs"] == 0
        assert result["changed"] == 0
