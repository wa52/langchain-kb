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

    async def test_tools_list_returns_three_tools(self, session):
        ac = session["client"]
        sid = session["session_id"]
        headers = {"mcp-session-id": sid, "Accept": "application/json"}
        body = {"jsonrpc": "2.0", "method": "tools/list", "id": 2}
        resp = await ac.post("/mcp", json=body, headers=headers)
        assert resp.status_code == 200
        tools = resp.json()["result"]["tools"]
        names = sorted(t["name"] for t in tools)
        assert names == ["answer_with_knowledge", "get_index_status", "search_knowledge"]

    async def test_excluded_tools_not_in_list(self, session):
        ac = session["client"]
        sid = session["session_id"]
        headers = {"mcp-session-id": sid, "Accept": "application/json"}
        body = {"jsonrpc": "2.0", "method": "tools/list", "id": 2}
        resp = await ac.post("/mcp", json=body, headers=headers)
        names = {t["name"] for t in resp.json()["result"]["tools"]}
        assert "health_check" not in names
        assert "start_index_task" not in names

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


class TestIndexToolCall:

    async def test_get_index_status_returns_task_status(self, session):
        from src.api.services.indexing import get_task_manager
        mgr = get_task_manager()
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
