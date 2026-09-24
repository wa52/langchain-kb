from unittest.mock import MagicMock, patch
import json

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def reset_singleton():
    from src.resources import ResourceManager
    ResourceManager._instance = None
    ResourceManager._lock = type(ResourceManager._lock)()
    yield
    ResourceManager._instance = None


@pytest.fixture
def rm():
    from src.resources import ResourceManager
    rm = ResourceManager.get_instance()
    rm._initialized = True
    mock_vs = MagicMock()
    mock_vs._collection.count.return_value = 42
    mock_kg = MagicMock()
    mock_kg.graph.number_of_nodes.return_value = 10
    mock_kg.graph.number_of_edges.return_value = 5
    rm.vector_store = mock_vs
    rm.graph = mock_kg
    rm.agent = MagicMock()
    return rm


@pytest.fixture
def client(rm):
    from src.api.app import create_app
    app = create_app()
    return TestClient(app)


class TestHealth:
    def test_health_ok(self, client):
        resp = client.get("/api/v1/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert body["vector_count"] == 42
        assert body["entity_count"] == 10
        assert isinstance(body["uptime"], float)
        assert isinstance(body["index_version"], int)

    def test_health_503_when_not_ready(self):
        from src.api.app import create_app
        app = create_app()
        c = TestClient(app)
        resp = c.get("/api/v1/health")
        assert resp.status_code == 503


class TestSearch:
    def test_search_returns_results(self, client, rm):
        fake_doc = MagicMock()
        fake_doc.id = "chunk_001"
        fake_doc.page_content = "LangChain is a framework"
        fake_doc.metadata = {"source": "doc.md"}
        rm.vector_store.similarity_search_with_relevance_scores.return_value = [
            (fake_doc, 0.95)
        ]

        resp = client.post("/api/v1/retrieval/search", json={
            "query": "LangChain",
            "top_k": 3,
        })
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["results"]) == 1
        r = body["results"][0]
        assert r["source"] == "doc.md"
        assert r["chunk_id"] == "chunk_001"
        assert r["score"] == 0.95
        assert r["content"] == "LangChain is a framework"
        assert isinstance(body["elapsed_ms"], float)

    def test_search_uses_top_k(self, client, rm):
        rm.vector_store.similarity_search_with_relevance_scores.return_value = []
        resp = client.post("/api/v1/retrieval/search", json={
            "query": "test",
            "top_k": 10,
        })
        assert resp.status_code == 200
        rm.vector_store.similarity_search_with_relevance_scores.assert_called_with(
            "test", k=10
        )

    def test_search_empty_query_rejected(self, client):
        resp = client.post("/api/v1/retrieval/search", json={"query": ""})
        assert resp.status_code == 422

    def test_search_top_k_out_of_range(self, client):
        resp = client.post("/api/v1/retrieval/search", json={
            "query": "test",
            "top_k": 100,
        })
        assert resp.status_code == 422


class TestRetrievalDebugger:
    def test_debug_returns_ranked_channel_scores_and_elapsed_time(self, client):
        from types import SimpleNamespace
        from src.domain.routing import ScoredDocument

        scored = [
            ScoredDocument(
                document=SimpleNamespace(
                    page_content="HALCON 找线例程代码",
                    metadata={"source": "找线例程.hdev", "chunk_id": "chunk-7"},
                ),
                dense_score=0.91,
                bm25_score=0.5,
                fusion_score=0.705,
                dense_rank=1,
                bm25_rank=2,
                final_rank=1,
            ),
        ]
        with patch("src.application.knowledge.retrieve_scored_documents", return_value=scored) as retrieve:
            response = client.post("/api/v1/retrieval/debug", json={
                "query": "HALCON 找线例程",
                "top_k": 4,
            })

        assert response.status_code == 200
        body = response.json()
        assert body["query"] == "HALCON 找线例程"
        assert body["results"] == [{
            "source": "找线例程.hdev",
            "chunk_id": "chunk-7",
            "content": "HALCON 找线例程代码",
            "dense_score": 0.91,
            "bm25_score": 0.5,
            "fusion_score": 0.705,
            "dense_rank": 1,
            "bm25_rank": 2,
            "rank": 1,
        }]
        assert isinstance(body["elapsed_ms"], (int, float))
        retrieve.assert_called_once_with("HALCON 找线例程", 4)

    def test_debug_rejects_empty_query_and_invalid_top_k(self, client):
        empty = client.post("/api/v1/retrieval/debug", json={"query": ""})
        too_many = client.post("/api/v1/retrieval/debug", json={
            "query": "test", "top_k": 100,
        })

        assert empty.status_code == 422
        assert too_many.status_code == 422

    def test_debug_returns_empty_results_without_error(self, client):
        with patch("src.application.knowledge.retrieve_scored_documents", return_value=[]):
            response = client.post("/api/v1/retrieval/debug", json={
                "query": "no matching source",
                "top_k": 5,
            })

        assert response.status_code == 200
        assert response.json()["results"] == []


class TestRetrievalEvaluationReport:
    def test_latest_report_returns_empty_state_when_no_baseline_exists(self, client, tmp_path):
        with patch("src.api.routers.retrieval.RETRIEVAL_EVAL_REPORT_PATH", tmp_path / "missing.json"):
            response = client.get("/api/v1/evaluations/retrieval/latest")

        assert response.status_code == 200
        assert response.json() == {
            "status": "empty",
            "report": None,
            "message": "尚无检索评测报告，请运行隔离基准后刷新。",
        }

    def test_latest_report_exposes_metrics_and_case_ranks_without_query_text(self, client, tmp_path):
        report_path = tmp_path / "latest.json"
        report_path.write_text(json.dumps({
            "report_version": 1,
            "evaluated_at": "2026-09-24T00:00:00+00:00",
            "environment": "isolated-frozen-example-corpus",
            "dataset_version": 1,
            "dataset_sha256": "a" * 64,
            "retrieval_profile": "src.application.knowledge.retrieve_scored_documents",
            "embedding_model": "bge-small-zh",
            "chunking": {"size": 500, "overlap": 80},
            "corpus": [{"source": "rag_concepts.md", "sha256": "b" * 64}],
            "metrics": {
                "total": 1,
                "recall_at_k": {"1": 1.0, "3": 1.0, "5": 1.0},
                "mrr": 1.0,
                "latency_ms": {"p50": 12.0, "p95": 12.0},
                "cases": [{
                    "case_id": "rag-core",
                    "relevant_ids": ["rag_concepts.md::0"],
                    "retrieved_relevant_ids": ["rag_concepts.md::0"],
                    "first_relevant_rank": 1,
                    "hits_at_k": {"1": 1, "3": 1, "5": 1},
                    "reciprocal_rank": 1.0,
                    "elapsed_ms": 12.0,
                }],
            },
        }), encoding="utf-8")
        with patch("src.api.routers.retrieval.RETRIEVAL_EVAL_REPORT_PATH", report_path):
            response = client.get("/api/v1/evaluations/retrieval/latest")

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "completed"
        assert body["report"]["metrics"]["recall_at_k"]["5"] == 1.0
        assert body["report"]["metrics"]["cases"][0]["first_relevant_rank"] == 1
        assert "query" not in body["report"]["metrics"]["cases"][0]


class TestChat:
    def test_chat_returns_answer(self, client):
        with (
            patch("src.api.services.chat._direct_answer", return_value="Hello world"),
            patch("src.api.services.chat.save_history", return_value="sess_123"),
        ):
            resp = client.post("/api/v1/chat", json={"query": "hi"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["answer"] == "Hello world"
        assert "citations" in body
        assert body["conversation_id"] == "sess_123"
        assert isinstance(body["elapsed_ms"], float)

    def test_chat_with_session_id(self, client):
        with (
            patch("src.api.services.chat._direct_answer", return_value="OK"),
            patch("src.api.services.chat.load_history", return_value=[{"role": "user", "content": "prev"}]),
            patch("src.api.services.chat.save_history", return_value="sess_456"),
        ):
            resp = client.post("/api/v1/chat", json={
                "query": "follow up",
                "session_id": "sess_456",
            })
        assert resp.status_code == 200
        assert resp.json()["conversation_id"] == "sess_456"

    def test_chat_empty_query_rejected(self, client):
        resp = client.post("/api/v1/chat", json={"query": ""})
        assert resp.status_code == 422


class TestIndexDocuments:
    def test_index_creates_task_and_starts_background(self, client, rm, tmp_path):
        d = tmp_path / "docs"
        d.mkdir()
        (d / "test.md").write_text("# hello", encoding="utf-8")

        # The endpoint only creates the task; patch the runner so the real
        # ingestion pipeline (embedding load + vector write + BM25 rebuild)
        # does not run against the real chroma_db/data dirs in tests.
        with patch("src.api.routers.indexing.run_index_task"):
            resp = client.post("/api/v1/documents/index", json={
                "path": str(d),
            })
        assert resp.status_code == 202
        body = resp.json()
        assert body["status"] == "pending"
        assert len(body["task_id"]) > 0

    def test_index_path_not_found(self, client, rm):
        resp = client.post("/api/v1/documents/index", json={
            "path": "/nonexistent",
        })
        assert resp.status_code == 400


class TestTaskPolling:
    def test_get_task_returns_status(self, client):
        from src.api.services.indexing import get_task_manager
        mgr = get_task_manager()
        tid = mgr.create_task("/some/path")
        mgr.update_task(tid, status="running")

        resp = client.get(f"/api/v1/index/tasks/{tid}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["task_id"] == tid
        assert body["status"] == "running"

    def test_get_task_not_found(self, client):
        resp = client.get("/api/v1/index/tasks/no-such-task")
        assert resp.status_code == 404

    def test_task_lifecycle(self, client):
        from src.api.services.indexing import get_task_manager
        mgr = get_task_manager()
        tid = mgr.create_task("/path")
        assert client.get(f"/api/v1/index/tasks/{tid}").json()["status"] == "pending"

        mgr.update_task(tid, status="running", progress="50%")
        body = client.get(f"/api/v1/index/tasks/{tid}").json()
        assert body["status"] == "running"
        assert body["progress"] == "50%"

        mgr.update_task(tid, status="done", result={"chunks_added": 15})
        body = client.get(f"/api/v1/index/tasks/{tid}").json()
        assert body["status"] == "done"
        assert body["result"]["chunks_added"] == 15


class TestErrorResponse:
    def test_unified_error_structure_on_404(self, client):
        resp = client.get("/api/v1/nonexistent")
        assert resp.status_code == 404
        body = resp.json()
        assert "detail" in body

    def test_unified_error_structure_on_422(self, client):
        resp = client.post("/api/v1/retrieval/search", json={})
        assert resp.status_code == 422
        body = resp.json()
        assert "error" in body or "detail" in body
