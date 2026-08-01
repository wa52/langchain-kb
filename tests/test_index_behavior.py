import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture(autouse=True)
def reset_singleton():
    from src.resources import ResourceManager
    ResourceManager._instance = None
    ResourceManager._lock = type(ResourceManager._lock)()
    yield
    ResourceManager._instance = None


@pytest.fixture(autouse=True)
def isolate_tracker(tmp_path):
    """Redirect the file tracker to a temp path so tests never touch the real
    data/file_tracker.json in the knowledge base."""
    import src.ingestion.tracker as tracker
    original = tracker.TRACKER_FILE
    tracker.TRACKER_FILE = str(tmp_path / "file_tracker.json")
    yield
    tracker.TRACKER_FILE = original


@pytest.fixture
def rm():
    from src.resources import ResourceManager
    rm = ResourceManager.get_instance()
    rm._initialized = True
    rm.vector_store = MagicMock()
    rm.graph = MagicMock()
    return rm


@pytest.fixture
def task_mgr():
    from src.api.services.indexing import get_task_manager
    mgr = get_task_manager()
    mgr._tasks.clear()
    return mgr


class TestIncrementalIndexing:
    def test_tracker_detects_unchanged_files(self, tmp_path):
        from src.ingestion.tracker import get_changed_files, update_tracker
        d = tmp_path / "docs"
        d.mkdir()
        f = d / "test.md"
        f.write_text("# hello", encoding="utf-8")
        update_tracker("internal", d)
        changed, unchanged = get_changed_files([(str(d), "internal")])
        assert len(changed) == 0
        assert len(unchanged) == 1

    def test_tracker_detects_new_file(self, tmp_path):
        from src.ingestion.tracker import get_changed_files, update_tracker
        d = tmp_path / "docs"
        d.mkdir()
        update_tracker("internal", d)
        f = d / "new.md"
        f.write_text("# new", encoding="utf-8")
        changed, unchanged = get_changed_files([(str(d), "internal")])
        assert len(changed) == 1
        assert len(unchanged) == 0

    def test_tracker_detects_modified_file(self, tmp_path):
        import time
        from src.ingestion.tracker import get_changed_files, update_tracker
        d = tmp_path / "docs"
        d.mkdir()
        f = d / "test.md"
        f.write_text("# v1 content that is long enough", encoding="utf-8")
        update_tracker("internal", d)
        time.sleep(1.1)
        f.write_text("# v2 much longer content to ensure different mtime and size", encoding="utf-8")
        changed, unchanged = get_changed_files([(str(d), "internal")])
        assert len(changed) == 1

    def test_tracker_empty_dir_no_files(self, tmp_path):
        from src.ingestion.tracker import get_changed_files, update_tracker
        d = tmp_path / "empty"
        d.mkdir()
        changed, unchanged = get_changed_files([(str(d), "internal")])
        assert len(changed) == 0
        assert len(unchanged) == 0


class TestIndexTaskDedup:
    def test_same_path_cannot_be_indexed_twice(self, task_mgr, rm):
        from fastapi.testclient import TestClient
        from src.api.app import create_app
        c = TestClient(create_app())
        import tempfile, os
        with tempfile.NamedTemporaryFile(suffix=".md", mode="w", delete=False) as tf:
            tf.write("# test")
            path = tf.name
        try:
            resp1 = c.post("/api/v1/documents/index", json={"path": path})
            assert resp1.status_code == 202
            resp2 = c.post("/api/v1/documents/index", json={"path": path})
            assert resp2.status_code == 409
            body = resp2.json()
            assert "detail" in body
        finally:
            os.unlink(path)

    def test_done_task_allows_reindex(self, task_mgr):
        mgr = task_mgr
        tid = mgr.create_task("/path/a.md")
        mgr.update_task(tid, status="done")
        tid2 = mgr.create_task("/path/a.md")
        assert tid2 != tid

    def test_has_active_task_true_for_pending(self, task_mgr):
        mgr = task_mgr
        mgr.create_task("/path/x.md")
        assert mgr.has_active_task("/path/x.md") is True

    def test_has_active_task_false_after_done(self, task_mgr):
        mgr = task_mgr
        tid = mgr.create_task("/path/y.md")
        mgr.update_task(tid, status="done")
        assert mgr.has_active_task("/path/y.md") is False


class TestConcurrentAccess:
    def test_index_does_not_block_search(self, rm):
        from fastapi.testclient import TestClient
        from src.api.app import create_app
        c = TestClient(create_app())

        with (
            patch("src.api.routers.indexing.run_index_task"),
        ):
            import tempfile, os
            with tempfile.NamedTemporaryFile(suffix=".md", mode="w", delete=False) as tf:
                tf.write("# concurrent")
                path = tf.name
            try:
                idx_resp = c.post("/api/v1/documents/index", json={"path": path})
                assert idx_resp.status_code == 202
                search_resp = c.post("/api/v1/retrieval/search", json={
                    "query": "test", "top_k": 3
                })
                assert search_resp.status_code == 200
            finally:
                os.unlink(path)

    def test_multiple_indices_sequential(self, task_mgr):
        mgr = task_mgr
        t1 = mgr.create_task("/path/1.md")
        mgr.update_task(t1, status="done")
        t2 = mgr.create_task("/path/2.md")
        mgr.update_task(t2, status="done")
        assert t1 != t2
        assert mgr.get_task(t1)["status"] == "done"
        assert mgr.get_task(t2)["status"] == "done"
