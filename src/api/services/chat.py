"""Compatibility composition for the transport-neutral conversation use case."""

import time
from typing import Iterator

from config import (
    ENABLE_GRAPH, ENABLE_HYBRID_SEARCH, HISTORY_COMPRESS_ROUNDS, HISTORY_MAX_TOKENS,
    FAST_RAG_FETCH_K, FAST_RAG_GATE_THRESHOLD, FAST_RAG_MAX_CONTEXT_TOKENS,
    FAST_RAG_TOP_K,
)
from src.agent.chat_history import allocate_session_id, load_history, save_history, session_lock
from src.agent.harness import verify_agent_run
from src.agent.query_router import DIRECT_SYSTEM_PROMPT, QueryRoute, parse_route_command, route_query
from src.agent.rag_agent import create_rag_agent, stream_rag_response
from src.application.citations import _CITATION_PATTERN, extract_sources
from src.application.conversation_service import ConversationService
from src.application.conversation_store import ConversationStore
from src.application.direct_chat import DirectChatEngine
from src.application.fast_rag import FastRagService
from src.application.smart_router import SmartRouteService
from src.application.source_enrichment import enrich_sources
from src.bootstrap.composition import create_agent_runtime

_EXCERPT_LIMIT = 200
_BASENAME_TTL = 60.0
_basename_index: dict[str, str] | None = None
_basename_index_ts = 0.0


def _get_agent(tool_names: tuple[str, ...] | None = None):
    from src.resources import ResourceManager
    try:
        manager = ResourceManager.get_instance()
        if manager.is_ready():
            return manager.get_agent(tool_names=tool_names)
    except Exception:
        pass
    agent = create_rag_agent(tool_names=tool_names)
    try:
        manager = ResourceManager.get_instance()
        if manager.is_ready():
            manager.agent = agent
    except Exception:
        pass
    return agent


def _agent_runtime():
    tool_registry = None
    try:
        from src.resources import ResourceManager
        manager = ResourceManager.get_instance()
        tool_registry = getattr(manager, "tool_registry", None)
        if tool_registry is not None:
            from src.agent.mcp_client import ensure_mcp_tools_registered
            ensure_mcp_tools_registered(tool_registry)
    except Exception:
        tool_registry = None
    if tool_registry is not None:
        from src.harness import JevToolSelector, RuleBasedToolSelector
        rule_selector = RuleBasedToolSelector(max_candidates=12)
        selector = JevToolSelector(rule_selector) if __import__("os").getenv("TYPESAFE_API_KEY") else rule_selector
        return create_agent_runtime(
            agent_factory=_get_agent,
            stream_fn=stream_rag_response,
            tool_registry=tool_registry,
            tool_selector=selector,
        )
    return create_agent_runtime(agent_factory=_get_agent, stream_fn=stream_rag_response)


def _get_direct_llm():
    try:
        from src.resources import ResourceManager
        manager = ResourceManager.get_instance()
        if manager.is_ready() and manager.llm is not None:
            return manager.llm
    except Exception:
        pass
    from src.llm import get_llm
    return get_llm(temperature=0)


def _estimated_tokens(text: str) -> int:
    cjk = sum("\u4e00" <= char <= "\u9fff" for char in text)
    return cjk + max(0, len(text) - cjk) // 4


def _direct_engine() -> DirectChatEngine:
    return DirectChatEngine(_get_direct_llm, DIRECT_SYSTEM_PROMPT, _estimated_tokens, HISTORY_MAX_TOKENS)


def _direct_messages(messages: list[dict]) -> list[dict]:
    return _direct_engine().prompt_messages(messages)


def _model_messages(messages: list[dict]) -> list[dict]:
    return DirectChatEngine.model_messages(messages)


def _trim_direct_history(messages: list[dict]) -> list[dict]:
    return _direct_engine().trim_history(messages)


def _direct_answer(messages: list[dict]) -> str:
    return _direct_engine().answer(messages)


def _stream_direct_answer(messages: list[dict]):
    yield from _direct_engine().stream(messages)


def _fast_rag_service() -> FastRagService:
    def retrieve(query: str, k: int):
        from src.application.knowledge import retrieve_documents
        return retrieve_documents(query, k)

    return FastRagService(
        retrieve=retrieve,
        llm_factory=_get_direct_llm,
        token_estimator=_estimated_tokens,
        top_k=FAST_RAG_TOP_K,
        fetch_k=FAST_RAG_FETCH_K,
        max_context_tokens=FAST_RAG_MAX_CONTEXT_TOKENS,
        gate_threshold=FAST_RAG_GATE_THRESHOLD,
    )


def _smart_router() -> SmartRouteService:
    def retrieve(query: str, k: int):
        from src.application.knowledge import retrieve_documents
        return retrieve_documents(query, k)

    return SmartRouteService(
        retrieve,
        fetch_k=FAST_RAG_FETCH_K,
        rag_threshold=FAST_RAG_GATE_THRESHOLD,
    )


def _maybe_compress_history(messages: list[dict]) -> list[dict]:
    if len(messages) < 2:
        return messages
    history, current = messages[:-1], messages[-1]
    turns = [message for message in history if message.get("role") == "user"]
    estimate = sum(_estimated_tokens(str(message.get("content", ""))) for message in history)
    if len(turns) <= HISTORY_COMPRESS_ROUNDS and estimate <= HISTORY_MAX_TOKENS:
        return messages
    if len(turns) > HISTORY_COMPRESS_ROUNDS:
        try:
            from src.resources import ResourceManager
            from src.agent.chat_history import compress_history
            manager = ResourceManager.get_instance()
            llm = manager.llm if manager.is_ready() else None
            compressed = compress_history(history, llm, keep_rounds=HISTORY_COMPRESS_ROUNDS)
            if compressed and compressed != history:
                return compressed + [current]
        except Exception:
            pass
    trimmed = history
    while len(trimmed) > 2 and sum(_estimated_tokens(str(m.get("content", ""))) for m in trimmed) > HISTORY_MAX_TOKENS:
        trimmed = trimmed[2:]
    return trimmed + [current]


def _serialize_messages(messages: list) -> list[dict]:
    return [
        message if isinstance(message, dict) else {
            "role": getattr(message, "type", getattr(message, "role", "")),
            "content": getattr(message, "content", ""),
        }
        for message in messages
    ]


def _conversation_store() -> ConversationStore:
    return ConversationStore(allocate_session_id, load_history, save_history, session_lock)


def _build_messages(query: str, session_id: str | None) -> list[dict]:
    """Compatibility helper; primary message assembly lives in ConversationService."""
    messages: list[dict] = []
    if session_id:
        for item in _conversation_store().load(session_id) or []:
            if isinstance(item, dict):
                message = {"role": item.get("role", ""), "content": item.get("content", "")}
                for key in ("route", "tools"):
                    if key in item:
                        message[key] = item[key]
                messages.append(message)
            else:
                messages.append({"role": getattr(item, "type", getattr(item, "role", "")), "content": getattr(item, "content", "")})
    return messages + [{"role": "user", "content": query}]


def _query_source(name: str) -> dict:
    try:
        from src.vector_store.chroma_client import get_vector_store
        result = get_vector_store()._collection.get(where={"source": name}, include=["documents", "metadatas"], limit=1)
        ids, docs, metas = result.get("ids") or [], result.get("documents") or [], result.get("metadatas") or []
        if ids and docs:
            text = docs[0] or ""
            excerpt = text[:_EXCERPT_LIMIT] + ("…" if len(text) > _EXCERPT_LIMIT else "")
            metadata = metas[0] if metas else {}
            return {"chunk_id": ids[0] or (metadata or {}).get("chunk_id", ""), "excerpt": excerpt}
    except Exception:
        pass
    return {"chunk_id": "", "excerpt": None}


def _build_basename_index() -> dict[str, str]:
    from src.vector_store.chroma_client import get_vector_store
    collection, mapping, offset = get_vector_store()._collection, {}, 0
    while True:
        batch = collection.get(include=["metadatas"], limit=500, offset=offset)
        metadata = batch.get("metadatas", []) if batch else []
        if not metadata:
            return mapping
        for item in metadata:
            source = (item or {}).get("source", "")
            if source:
                mapping.setdefault(source.replace("\\", "/").rsplit("/", 1)[-1], source)
        offset += 500


def _basename_to_source(name: str) -> str | None:
    global _basename_index, _basename_index_ts
    if _basename_index is None or time.time() - _basename_index_ts > _BASENAME_TTL:
        try:
            _basename_index = _build_basename_index()
        except Exception:
            _basename_index = {}
        _basename_index_ts = time.time()
    return _basename_index.get(name)


def _source_lookup(name: str) -> dict:
    found = _query_source(name)
    if found["chunk_id"] or "/" in name or "\\" in name:
        return found
    full_name = _basename_to_source(name)
    return _query_source(full_name) if full_name and full_name != name else found


def _hit_chain() -> list[str]:
    return ["vector", *(["bm25"] if ENABLE_HYBRID_SEARCH else []), *(["graph"] if ENABLE_GRAPH else [])]


def build_sources(answer: str) -> list[dict]:
    return enrich_sources(answer, extract_sources=extract_sources, source_lookup=_source_lookup, hit_chain=_hit_chain)


def _resume_command(decisions: list[str], message: str | None):
    from langgraph.types import Command
    return Command(resume={"decisions": [{"type": item, **({"message": message} if message else {})} for item in decisions]})


def _conversation_service() -> ConversationService:
    return ConversationService(
        store_factory=_conversation_store, route_query=route_query, parse_command=parse_route_command,
        direct_route=QueryRoute.DIRECT, fast_rag_route=QueryRoute.FAST_RAG,
        agent_route=QueryRoute.AGENT, direct_answer=_direct_answer, stream_direct_answer=_stream_direct_answer,
        trim_direct_history=_trim_direct_history, model_messages=_model_messages, compress_history=_maybe_compress_history,
        agent_runtime_factory=_agent_runtime, serialize_messages=_serialize_messages, build_sources=build_sources,
        verify_agent_run=verify_agent_run, resume_command=_resume_command,
        fast_rag_service=_fast_rag_service(),
        smart_router=_smart_router(),
    )


def chat_with_rag(query: str, session_id: str | None = None) -> tuple[str, str, float]:
    return _conversation_service().answer(query, session_id)


def stream_chat_events(query: str, session_id: str | None, stop_event) -> Iterator[dict]:
    yield from _conversation_service().stream(query, session_id, stop_event)


def resume_chat_events(session_id: str, decision: str, message: str | None, stop_event, decisions: list[str] | None = None) -> Iterator[dict]:
    yield from _conversation_service().resume(session_id, decision, message, stop_event, decisions)
