"""Knowledge overview + upload tests at the HTTP seam."""

from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def reset_singleton():
    from src.resources import ResourceManager
    from src.api.services.indexing import get_task_manager
    ResourceManager._instance = None
    ResourceManager._lock = type(ResourceManager._lock)()
    get_task_manager().clear()
    yield
    ResourceManager._instance = None
    get_task_manager().clear()


@pytest.fixture
def rm():
    from src.resources import ResourceManager
    rm = ResourceManager.get_instance()
    rm._initialized = True
    mock_vs = MagicMock()
    mock_vs._collection.count.return_value = 42
    mock_vs._collection.get.return_value = {"metadatas": [{"source": "doc.md"}]}
    mock_kg = MagicMock()
    mock_kg.graph.number_of_nodes.return_value = 10
    mock_kg.graph.number_of_edges.return_value = 5
    rm.vector_store = mock_vs
    rm.graph = mock_kg
    rm.llm = MagicMock()
    rm.agent = MagicMock()
    return rm


@pytest.fixture
def client(rm):
    from src.api.app import create_app
    return TestClient(create_app())


class TestKnowledgeStats:
    def test_stats_shape(self, client, rm, monkeypatch):
        monkeypatch.setattr("src.ingestion.tracker.list_all_files", lambda: [{"file_key": "doc.md"}])
        with patch("src.retrieval.retriever._bm25_retriever") as mock_bm25:
            mock_bm25.docs = [1, 2, 3]
            resp = client.get("/api/v1/knowledge/stats")
        assert resp.status_code == 200
        body = resp.json()
        assert body["documents"] == 1
        assert body["chunks"] == 42
        assert body["bm25_chunks"] == 3
        assert body["graph"] == {"entities": 10, "relations": 5}
        assert body["index_task"] is None

    def test_stats_include_latest_index_task(self, client, rm, monkeypatch):
        monkeypatch.setattr("src.ingestion.tracker.list_all_files", lambda: [])
        from src.api.services.indexing import get_task_manager
        mgr = get_task_manager()
        mgr.update_task(
            mgr.create_task("/tmp/x.md"),
            status="done",
            progress="Complete",
            result={"chunks_added": 7},
        )
        resp = client.get("/api/v1/knowledge/stats")
        body = resp.json()
        task = body["index_task"]
        assert task is not None
        assert task["status"] == "done"
        assert task["result"] == {"chunks_added": 7}

    def test_stats_empty_graph_defaults(self, client, rm, monkeypatch):
        monkeypatch.setattr("src.ingestion.tracker.list_all_files", lambda: [])
        rm.graph = None
        resp = client.get("/api/v1/knowledge/stats")
        body = resp.json()
        assert body["graph"] == {"entities": 0, "relations": 0}


class TestUploadDocuments:
    def test_upload_saves_and_creates_tasks(self, client, rm, tmp_path, monkeypatch):
        monkeypatch.setattr("config.EXTERNAL_DIR", str(tmp_path / "external"))
        files = [
            ("files", ("a.md", BytesIO(b"# hello a"), "text/markdown")),
            ("files", ("b.md", BytesIO(b"# hello b"), "text/markdown")),
        ]
        with patch("src.api.routers.indexing.run_index_task"):
            resp = client.post("/api/v1/documents/upload", files=files)
        assert resp.status_code == 202
        body = resp.json()
        assert len(body["tasks"]) == 2
        assert all(t["status"] == "pending" for t in body["tasks"])
        assert sorted(body["saved"]) == ["a.md", "b.md"]
        assert (tmp_path / "external" / "a.md").exists()
        assert (tmp_path / "external" / "b.md").exists()

    def test_upload_runs_task_in_place(self, client, rm, tmp_path, monkeypatch):
        monkeypatch.setattr("config.EXTERNAL_DIR", str(tmp_path / "external"))
        calls = []

        async def fake_run(task_id, path, in_place=False):
            calls.append((task_id, path, in_place))

        with patch("src.api.routers.indexing.run_index_task", side_effect=fake_run):
            resp = client.post(
                "/api/v1/documents/upload",
                files=[("files", ("c.md", BytesIO(b"# c"), "text/markdown"))],
            )
        assert resp.status_code == 202
        assert len(calls) == 1
        _, path, in_place = calls[0]
        assert in_place is True
        assert str(tmp_path / "external" / "c.md") == path

    def test_upload_dedups_filenames(self, client, rm, tmp_path, monkeypatch):
        monkeypatch.setattr("config.EXTERNAL_DIR", str(tmp_path / "external"))
        (tmp_path / "external").mkdir(parents=True)
        (tmp_path / "external" / "d.md").write_text("existing", encoding="utf-8")
        with patch("src.api.routers.indexing.run_index_task"):
            resp = client.post(
                "/api/v1/documents/upload",
                files=[("files", ("d.md", BytesIO(b"# new"), "text/markdown"))],
            )
        assert resp.status_code == 202
        assert resp.json()["saved"] == ["d_1.md"]
        assert (tmp_path / "external" / "d_1.md").exists()

    def test_upload_sanitizes_path_traversal(self, client, rm, tmp_path, monkeypatch):
        monkeypatch.setattr("config.EXTERNAL_DIR", str(tmp_path / "external"))
        with patch("src.api.routers.indexing.run_index_task"):
            resp = client.post(
                "/api/v1/documents/upload",
                files=[("files", ("../../evil.md", BytesIO(b"# e"), "text/markdown"))],
            )
        assert resp.status_code == 202
        assert resp.json()["saved"] == ["evil.md"]
        assert not (tmp_path / "external" / ".." / "evil.md").exists()

    def test_upload_no_files_rejected(self, client, rm):
        resp = client.post("/api/v1/documents/upload")
        assert resp.status_code == 422

    def test_upload_oversized_rejected(self, client, rm, tmp_path, monkeypatch):
        monkeypatch.setattr("config.EXTERNAL_DIR", str(tmp_path / "external"))
        big = BytesIO(b"x" * (50 * 1024 * 1024 + 1))
        with patch("src.api.routers.indexing.run_index_task"):
            resp = client.post(
                "/api/v1/documents/upload",
                files=[("files", ("big.md", big, "text/markdown"))],
            )
        assert resp.status_code == 413
