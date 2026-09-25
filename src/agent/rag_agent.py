from deepagents import create_deep_agent
import inspect

from config import ENABLE_HYBRID_SEARCH, ENABLE_GRAPH
from src.agent.model_trace import ModelTraceCallbacks as _ModelTraceCallbacks
from src.agent.tools import retrieve_knowledge, retrieve_graph, save_research_material
from src.agent.project_workflow import project_workflow
from src.agent.prompt import build_agent_prompt
from src.vector_store.embedding import get_embedding_model
from src.vector_store.service import VectorStoreService
from src.vector_store.chroma_client import get_vector_store
from src.llm import get_llm
from src.agent.harness import ToolRecoveryMiddleware

SYSTEM_PROMPT = build_agent_prompt()


def create_rag_agent(tool_registry=None, tool_names: tuple[str, ...] | None = None):
    import os as _os
    import time as _time
    from src.status import get_registry
    get_registry().set_loading("agent", "构建 RAG Agent")
    _os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"
    import logging
    logging.getLogger("huggingface_hub").setLevel(logging.WARNING)
    logging.getLogger("sentence_transformers").setLevel(logging.WARNING)

    _t0 = _time.time()
    get_embedding_model()
    print(f"  [计时] 加载 embedding 模型: {_time.time() - _t0:.2f}s")

    _t1 = _time.time()
    get_vector_store()
    print(f"  [计时] 连接向量库: {_time.time() - _t1:.2f}s")

    if ENABLE_HYBRID_SEARCH:
        _t2 = _time.time()
        VectorStoreService().rebuild_bm25()
        print(f"  [计时] 构建/加载 BM25 索引: {_time.time() - _t2:.2f}s")

    _t3 = _time.time()
    model = get_llm(temperature=0)
    print(f"  [计时] 初始化 LLM: {_time.time() - _t3:.2f}s")

    tools = tool_registry.langchain_tools(tool_names) if tool_registry is not None else []
    if tool_registry is not None:
        try:
            from src.agent.mcp_client import ensure_mcp_tools_registered
            ensure_mcp_tools_registered(tool_registry)
            tools = tool_registry.langchain_tools(tool_names)
        except Exception as exc:
            print(f"  [MCP] 外部工具加载失败（不影响本地工具）: {exc}")
    if not tools:
        tools = [retrieve_knowledge, project_workflow, save_research_material]
        if ENABLE_GRAPH:
            tools.append(retrieve_graph)

    # Load external MCP tools (opencode-style mcp.json). Degrades gracefully:
    # a failure here never blocks the local knowledge tools.
    external_names: list[str] = [getattr(t, "name", "external") for t in tools if getattr(t, "name", "").startswith("mcp_")]
    external_tools = []
    if tool_registry is None:
        try:
            from src.agent.mcp_client import load_mcp_tools, default_mcp_config_path
            external = load_mcp_tools(default_mcp_config_path())
            if external:
                tools.extend(external)
                external_tools = external
                external_names = [getattr(t, "name", "external") for t in external]
                print(f"  [MCP] 已加载 {len(external)} 个外部工具")
        except Exception as e:
            print(f"  [MCP] 外部工具加载失败（不影响本地工具）: {e}")

    _t4 = _time.time()
    prompt = build_agent_prompt(external_names)
    checkpointer, checkpoint_connection = _create_checkpointer()
    interrupt_on = {name: True for name in ("write_file", "edit_file", "execute", "index_local_path")}
    for tool in external_tools:
        name = getattr(tool, "name", "").lower()
        if any(word in name for word in ("write", "delete", "remove", "move", "rename", "execute", "run")):
            interrupt_on[getattr(tool, "name")] = True
    agent = create_deep_agent(
        model=model,
        tools=tools,
        system_prompt=prompt,
        checkpointer=checkpointer,
        interrupt_on=interrupt_on,
        middleware=[ToolRecoveryMiddleware()],
    )
    if checkpoint_connection is not None:
        agent._checkpoint_connection = checkpoint_connection
    get_registry().set_ready("agent", "Deep Agent")
    print(f"  [计时] 构建 Deep Agent: {_time.time() - _t4:.2f}s")
    return agent


def _create_checkpointer():
    """Create the durable saver, with an explicit in-memory fallback."""
    from config import CHECKPOINT_DB_PATH
    try:
        import sqlite3
        from pathlib import Path
        from langgraph.checkpoint.sqlite import SqliteSaver

        Path(CHECKPOINT_DB_PATH).parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(CHECKPOINT_DB_PATH, check_same_thread=False)
        saver = SqliteSaver(connection)
        saver.setup()
        return saver, connection
    except Exception as exc:
        from langgraph.checkpoint.memory import MemorySaver
        print(f"  [Agent] SQLite checkpoint 不可用，降级为内存模式: {exc}")
        return MemorySaver(), None


def close_agent_checkpoint(agent) -> None:
    """Close the SQLite connection owned by an Agent, if one exists."""
    connection = getattr(agent, "_checkpoint_connection", None)
    if connection is not None:
        connection.close()
        agent._checkpoint_connection = None


def _stream_with_callbacks(agent, input_value, callbacks):
    try:
        parameters = inspect.signature(agent.stream).parameters
        if "config" in parameters or any(
            parameter.kind == inspect.Parameter.VAR_KEYWORD
            for parameter in parameters.values()
        ):
            return agent.stream(input_value, config={"callbacks": [callbacks]})
    except (TypeError, ValueError):
        pass
    return agent.stream(input_value)


def stream_rag_response(agent, messages: list, on_tool=None, on_interrupt=None, on_tool_result=None, on_llm=None, on_model_start=None, on_model_end=None, on_model_error=None, stream_input=None):
    def content_length(value) -> int:
        if isinstance(value, str):
            return len(value)
        if isinstance(value, list):
            total = 0
            for item in value:
                if isinstance(item, dict):
                    total += len(str(item.get("text", item.get("content", ""))))
                else:
                    total += len(str(getattr(item, "text", item)))
            return total
        return len(str(value)) if value else 0

    tool_called = False
    seen_tool_ids = set()
    pending_tool_calls: dict[str, dict] = {}

    def remember_tool_calls(message) -> None:
        """Keep the arguments until the matching ToolMessage arrives."""
        for call in getattr(message, "tool_calls", None) or []:
            if not isinstance(call, dict):
                continue
            call_id = call.get("id")
            if call_id is None:
                continue
            arguments = call.get("args", call.get("arguments", {}))
            pending_tool_calls[str(call_id)] = {
                "name": str(call.get("name", "") or "tool"),
                "arguments": arguments if isinstance(arguments, dict) else {},
            }

    def attach_retrieval_timing(result: dict) -> dict:
        """Attach the completed RAG record without changing Tool/SSE behavior."""
        if result["name"] != "retrieve_knowledge":
            return result
        query = result.get("arguments", {}).get("query")
        if not isinstance(query, str):
            return result
        from src.retrieval.telemetry import retrieval_record_store

        record = retrieval_record_store.latest_for_query(" ".join(query.strip().split()))
        if record is not None:
            result["retrieval"] = record
            result["elapsed_ms"] = record.get("elapsed_ms")
        return result

    input_value = stream_input if stream_input is not None else {"messages": messages}
    callbacks = _ModelTraceCallbacks(on_model_start, on_model_end, on_model_error)
    for event in _stream_with_callbacks(agent, input_value, callbacks):
        if "__interrupt__" in event:
            if on_interrupt is not None:
                on_interrupt(event["__interrupt__"])
            continue
        for node_name, value in event.items():
            if not isinstance(value, dict) or "messages" not in value:
                continue
            for msg in value["messages"]:
                mtype = getattr(msg, "type", "")
                content = getattr(msg, "content", "") or ""
                if mtype == "ai":
                    remember_tool_calls(msg)
                if mtype == "ai" and content:
                    if on_llm is not None:
                        on_llm({"has_tool_calls": bool(getattr(msg, "tool_calls", None)), "content_length": len(str(content))})
                    yield content
                elif mtype == "tool" and not tool_called:
                    tool_called = True
                    n = content_length(content)
                    yield f"\n  [知识库检索完成 ({n} 字符)]\n\n"
                if on_tool is not None and mtype == "tool":
                    tid = getattr(msg, "tool_call_id", None) or getattr(msg, "id", None)
                    if tid is not None and tid in seen_tool_ids:
                        continue
                    if tid is not None:
                        seen_tool_ids.add(tid)
                    on_tool(getattr(msg, "name", "") or "tool")
                    if on_tool_result is not None:
                        tool_call = pending_tool_calls.get(str(tid), {}) if tid is not None else {}
                        result = attach_retrieval_timing({
                            "name": getattr(msg, "name", "") or "tool",
                            "status": getattr(msg, "status", None) or "success",
                            "content": content,
                            "tool_call_id": str(tid) if tid is not None else None,
                            "arguments": tool_call.get("arguments", {}),
                        })
                        on_tool_result(result)
