from unittest.mock import MagicMock, patch

import pytest
import httpx
from httpx import ASGITransport
from langchain_core.retrievers import BaseRetriever

pytestmark = pytest.mark.anyio


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
    mock_vs.as_retriever.return_value = MagicMock(spec=BaseRetriever)
    mock_kg = MagicMock()
    mock_kg.graph.number_of_nodes.return_value = 10
    mock_kg.graph.number_of_edges.return_value = 5
    rm.vector_store = mock_vs
    rm.graph = mock_kg
    rm.agent = MagicMock()
    return rm


_INIT_BODY = {
    "jsonrpc": "2.0",
    "method": "initialize",
    "id": 1,
    "params": {
        "protocolVersion": "0.1.0",
        "capabilities": {},
        "clientInfo": {"name": "test", "version": "1.0"},
    },
}


@pytest.fixture
async def session(rm):
    from src.api.app import create_app
    app = create_app()
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post("/mcp", json=_INIT_BODY, headers={"Accept": "application/json"})
        assert resp.status_code == 200, f"Init failed: {resp.text[:200]}"
        sess_id = resp.headers.get("mcp-session-id")
        assert sess_id is not None
        yield {"client": ac, "session_id": sess_id}


class TestToolDiscovery:

    async def test_tools_list_returns_expected_tools(self, session):
        ac = session["client"]
        sid = session["session_id"]
        headers = {"mcp-session-id": sid, "Accept": "application/json"}
        body = {"jsonrpc": "2.0", "method": "tools/list", "id": 2}
        resp = await ac.post("/mcp", json=body, headers=headers)
        assert resp.status_code == 200
        tools = resp.json()["result"]["tools"]
        names = sorted(t["name"] for t in tools)
        assert names == [
            "answer_with_knowledge",
            "get_index_status",
            "search_knowledge",
            "system_status",
        ]

    async def test_excluded_tools_not_in_list(self, session):
        forbidden = {"health_check", "index_document", "delete_document",
                       "reset_vector_store", "rebuild_all_indexes",
                       "change_model_config", "execute_script",
                       "start_index_task", "upload_documents", "remove_file",
                       "delete_session", "set_graph_extraction_mode",
                       "add_sync_dir", "remove_sync_dir", "run_sync"}
        ac = session["client"]
        sid = session["session_id"]
        headers = {"mcp-session-id": sid, "Accept": "application/json"}
        body = {"jsonrpc": "2.0", "method": "tools/list", "id": 2}
        resp = await ac.post("/mcp", json=body, headers=headers)
        names = {t["name"] for t in resp.json()["result"]["tools"]}
        for f in forbidden:
            assert f not in names, f"Forbidden tool exposed: {f}"

    async def test_search_knowledge_has_query_and_top_k_params(self, session):
        ac = session["client"]
        sid = session["session_id"]
        headers = {"mcp-session-id": sid, "Accept": "application/json"}
        body = {"jsonrpc": "2.0", "method": "tools/list", "id": 2}
        resp = await ac.post("/mcp", json=body, headers=headers)
        tools = resp.json()["result"]["tools"]
        search_tool = next(t for t in tools if t["name"] == "search_knowledge")
        props = search_tool["inputSchema"].get("properties", {})
        assert "query" in props
        assert "top_k" in props


class TestSearchToolCall:

    async def test_search_knowledge_returns_results(self, session, rm):
        ac = session["client"]
        sid = session["session_id"]

        fake_doc = MagicMock()
        fake_doc.id = "chunk_001"
        fake_doc.page_content = "LangChain is a framework"
        fake_doc.metadata = {"source": "doc.md"}
        rm.vector_store.similarity_search_with_relevance_scores.return_value = [
            (fake_doc, 0.95)
        ]

        headers = {"mcp-session-id": sid, "Accept": "application/json"}
        body = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "id": 3,
            "params": {
                "name": "search_knowledge",
                "arguments": {"query": "LangChain", "top_k": 3},
            },
        }
        resp = await ac.post("/mcp", json=body, headers=headers)
        assert resp.status_code == 200
        result = resp.json()
        assert "result" in result
        content = result["result"]["content"]
        text = "".join(c["text"] for c in content)
        assert "chunk_001" in text
        assert "LangChain is a framework" in text


class TestChatToolCall:

    async def test_answer_with_knowledge_returns_answer(self, session):
        ac = session["client"]
        sid = session["session_id"]

        with (
            patch("src.api.services.chat.create_rag_agent", return_value=MagicMock()),
            patch("src.api.services.chat.stream_rag_response", return_value=["Hello ", "world"]),
            patch("src.api.services.chat.save_history", return_value="sess_123"),
        ):
            headers = {"mcp-session-id": sid, "Accept": "application/json"}
            body = {
                "jsonrpc": "2.0",
                "method": "tools/call",
                "id": 4,
                "params": {
                    "name": "answer_with_knowledge",
                    "arguments": {"query": "hi"},
                },
            }
            resp = await ac.post("/mcp", json=body, headers=headers)
        assert resp.status_code == 200
        result = resp.json()
        assert "result" in result
        content = result["result"]["content"]
        text = "".join(c["text"] for c in content)
        assert "Hello world" in text
        assert "conversation_id" in text
        assert "sess_123" in text


class TestOpenAPISchema:

    async def test_operation_ids_match_expected(self, session):
        from src.api.app import create_app
        app = create_app()
        schema = app.openapi()
        oids = set()
        for path, methods in schema.get("paths", {}).items():
            for method, details in methods.items():
                oids.add(details.get("operationId"))
        expected = {"health_check", "search_knowledge", "answer_with_knowledge",
                     "chat_stream", "resume_chat", "start_index_task", "upload_documents",
                     "get_index_status", "system_status", "knowledge_stats",
                     "run_diagnostics", "get_diagnostics_status", "repair_diagnostics",
                     "list_sessions", "get_session", "delete_session",
                     "get_settings", "set_graph_extraction_mode",
                     "get_sync_status", "add_sync_dir", "remove_sync_dir", "run_sync",
                     "list_files", "remove_file"}
        assert oids == expected, f"Mismatch: {oids} vs {expected}"

    async def test_mcp_instance_stored_in_app_state(self, session):
        from src.api.app import create_app
        app = create_app()
        assert hasattr(app.state, "mcp")
        assert app.state.mcp is not None


class TestResourceReuse:

    async def test_consecutive_tool_calls_reuse_resources(self, session, rm):
        ac = session["client"]
        sid = session["session_id"]
        headers = {"mcp-session-id": sid, "Accept": "application/json"}

        rm.vector_store.similarity_search_with_relevance_scores.return_value = [
            (MagicMock(id="c1", page_content="a", metadata={"source": "x.md"}), 0.9)
        ]

        body = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "id": 10,
            "params": {"name": "search_knowledge", "arguments": {"query": "a", "top_k": 1}},
        }
        resp1 = await ac.post("/mcp", json=body, headers=headers)
        assert resp1.status_code == 200

        resp2 = await ac.post("/mcp", json=body, headers=headers)
        assert resp2.status_code == 200

    async def test_rest_still_callable_after_mcp(self, session, rm):
        from src.api.schemas import HealthResponse
        ac = session["client"]
        resp = await ac.get("/api/v1/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert body["vector_count"] == 42


class TestIndexToolCall:

    async def test_get_index_status_returns_task_status(self, session):
        from src.api.services.indexing import get_task_manager
        mgr = get_task_manager()
        # Order-independent: other tests may have left tasks (e.g. a pending
        # "/some/path" from test_api_routes) in this module-level singleton.
        mgr.clear()
        tid = mgr.create_task("/some/path")
        mgr.update_task(tid, status="running", progress="50%")

        ac = session["client"]
        sid = session["session_id"]
        headers = {"mcp-session-id": sid, "Accept": "application/json"}
        body = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "id": 5,
            "params": {
                "name": "get_index_status",
                "arguments": {"task_id": tid},
            },
        }
        resp = await ac.post("/mcp", json=body, headers=headers)
        assert resp.status_code == 200
        result = resp.json()
        assert "result" in result
        content = result["result"]["content"]
        text = "".join(c["text"] for c in content)
        assert tid in text
        assert "running" in text
        assert "50%" in text
        mgr.clear()


class TestSystemStatusToolCall:

    async def test_system_status_returns_status(self, session):
        ac = session["client"]
        sid = session["session_id"]
        headers = {"mcp-session-id": sid, "Accept": "application/json"}
        body = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "id": 6,
            "params": {"name": "system_status", "arguments": {}},
        }
        resp = await ac.post("/mcp", json=body, headers=headers)
        assert resp.status_code == 200
        result = resp.json()
        assert "result" in result
        content = result["result"]["content"]
        text = "".join(c["text"] for c in content)
        assert "vector_count" in text
        assert "42" in text
        assert "components" in text
