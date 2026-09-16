import re
import time
from typing import Iterator

from src.agent.rag_agent import create_rag_agent, stream_rag_response
from src.agent.chat_history import allocate_session_id, save_history, load_history, session_lock
from config import ENABLE_HYBRID_SEARCH, ENABLE_GRAPH, HISTORY_COMPRESS_ROUNDS, HISTORY_MAX_TOKENS

_CITATION_PATTERN = re.compile(r"\[来源:\s*([^\]]{1,256})\]")
_EXCERPT_LIMIT = 200
_BASENAME_TTL = 60.0


def _get_agent():
    """Return the RAG agent, reused across requests via ResourceManager.

    Delegates to the thread-safe, lock-protected ResourceManager.get_agent()
    so concurrent first requests build exactly one agent. Falls back to a
    local build only when the manager is not ready. Keeps a module-level
    reference to create_rag_agent so tests can patch it."""
    from src.resources import ResourceManager
    try:
        rm = ResourceManager.get_instance()
        if rm.is_ready():
            return rm.get_agent()
    except Exception:
        pass
    agent = create_rag_agent()
    try:
        rm = ResourceManager.get_instance()
        if rm.is_ready():
            rm.agent = agent
    except Exception:
        pass
    return agent


def _build_messages(query: str, session_id: str | None) -> list[dict]:
    messages: list[dict] = []
    if session_id:
        saved = load_history(session_id)
        for m in saved or []:
            if isinstance(m, dict):
                messages.append({"role": m.get("role", ""), "content": m.get("content", "")})
            else:
                messages.append({
                    "role": getattr(m, "type", getattr(m, "role", "")),
                    "content": getattr(m, "content", ""),
                })
    messages.append({"role": "user", "content": query})
    return messages


def _estimated_tokens(text: str) -> int:
    """Rough token estimate: CJK ≈ 1 token/char, latin ≈ 1 token/4 chars."""
    cjk = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
    other = max(0, len(text) - cjk)
    return cjk + other // 4


def _maybe_compress_history(messages: list[dict]) -> list[dict]:
    """Keep the history sent to the agent within budget. The current user
    message is never touched.

    - Too many rounds  -> LLM summary of the old part + recent rounds.
    - Only over token budget -> drop the oldest user/assistant pairs until
      the estimated tokens fit (no API cost).
    Falls back to the raw history on any failure.
    """
    if len(messages) < 2:
        return messages
    history = messages[:-1]
    current = messages[-1]
    user_turns = [m for m in history if m.get("role") == "user"]
    est = sum(_estimated_tokens(str(m.get("content", ""))) for m in history)
    if len(user_turns) <= HISTORY_COMPRESS_ROUNDS and est <= HISTORY_MAX_TOKENS:
        return messages
    if len(user_turns) > HISTORY_COMPRESS_ROUNDS:
        from src.resources import ResourceManager
        rm = ResourceManager.get_instance()
        llm = rm.llm if (rm.is_ready() and getattr(rm, "llm", None) is not None) else None
        try:
            from src.agent.chat_history import compress_history
            compressed = compress_history(history, llm, keep_rounds=HISTORY_COMPRESS_ROUNDS)
            if compressed and compressed != history:
                print(f"  [上下文] 历史过长（{len(user_turns)} 轮 / {est} tokens），压缩为摘要 + 最近 {HISTORY_COMPRESS_ROUNDS} 轮")
                return compressed + [current]
        except Exception:
            pass
    trimmed = history
    while len(trimmed) > 2 and sum(_estimated_tokens(str(m.get("content", ""))) for m in trimmed) > HISTORY_MAX_TOKENS:
        trimmed = trimmed[2:]
    if len(trimmed) != len(history):
        print(f"  [上下文] 历史超出 token 预算，截断最早 {len(history) - len(trimmed)} 条消息")
        return trimmed + [current]
    return messages


def _serialize_messages(messages: list) -> list[dict]:
    serializable = []
    for m in messages:
        if isinstance(m, dict):
            serializable.append(m)
        else:
            serializable.append({
                "role": getattr(m, "type", getattr(m, "role", "")),
                "content": getattr(m, "content", ""),
            })
    return serializable


def extract_sources(answer: str) -> list[dict]:
    """Extract `[来源: 文件名]` annotations into source items."""
    seen = set()
    sources = []
    for match in _CITATION_PATTERN.finditer(answer):
        source = match.group(1).strip()
        if source and source not in seen:
            seen.add(source)
            sources.append({"source": source, "chunk_id": "", "excerpt": None})
    return sources


_basename_index: dict[str, str] | None = None
_basename_index_ts: float = 0.0


def _query_source(name: str) -> dict:
    """Fetch the first vector-store chunk whose ``source`` equals ``name``."""
    try:
        from src.vector_store.chroma_client import get_vector_store
        vs = get_vector_store()
        col = vs._collection
        res = col.get(where={"source": name}, include=["documents", "metadatas"], limit=1)
        ids = res.get("ids") or []
        docs = res.get("documents") or []
        metas = res.get("metadatas") or []
        if ids and docs:
            text = docs[0] or ""
            meta = (metas[0] or {}) if metas else {}
            excerpt = text
            if len(excerpt) > _EXCERPT_LIMIT:
                excerpt = excerpt[:_EXCERPT_LIMIT] + "…"
            return {"chunk_id": ids[0] or meta.get("chunk_id", ""), "excerpt": excerpt}
    except Exception:
        pass
    return {"chunk_id": "", "excerpt": None}


def _build_basename_index() -> dict[str, str]:
    """Map stored ``source`` basename -> full stored path (metadata scan).

    Stored sources are relative paths (``sub/dir.md``) for directory loads
    while the agent cites basenames; the index lets a basename citation fall
    back to the real chunk. Metadata-only scan, cached briefly below."""
    from src.vector_store.chroma_client import get_vector_store
    vs = get_vector_store()
    col = vs._collection
    mapping: dict[str, str] = {}
    batch_size = 500
    offset = 0
    while True:
        batch = col.get(include=["metadatas"], limit=batch_size, offset=offset)
        metas = batch.get("metadatas", []) if batch else []
        if not metas:
            break
        for m in metas:
            src = (m or {}).get("source", "")
            if src:
                base = src.replace("\\", "/").rsplit("/", 1)[-1]
                mapping.setdefault(base, src)
        offset += batch_size
    return mapping


def _basename_to_source(name: str) -> str | None:
    """Full stored source path for a basename, using a short-TTL cache."""
    global _basename_index, _basename_index_ts
    now = time.time()
    if _basename_index is None or (now - _basename_index_ts) > _BASENAME_TTL:
        try:
            _basename_index = _build_basename_index()
        except Exception:
            _basename_index = {}
        _basename_index_ts = now
    return _basename_index.get(name)


def _source_lookup(name: str) -> dict:
    """Best-effort: chunk_id + excerpt for a cited source filename.

    Exact-match first; when the name is a bare basename and the exact match
    misses, fall back through the stored-source basename index (handles
    nested directory loads). Never raises."""
    found = _query_source(name)
    if found.get("chunk_id"):
        return found
    if "/" not in name and "\\" not in name:
        full = _basename_to_source(name)
        if full and full != name:
            found = _query_source(full)
            if found.get("chunk_id"):
                return found
    return {"chunk_id": "", "excerpt": None}


def _hit_chain() -> list[str]:
    """Engines the retrieval pipeline may have contributed for an answer."""
    chain = ["vector"]
    if ENABLE_HYBRID_SEARCH:
        chain.append("bm25")
    if ENABLE_GRAPH:
        chain.append("graph")
    return chain


def build_sources(answer: str) -> list[dict]:
    """Extract source markers and enrich them with chunk/excerpt/chain."""
    sources = extract_sources(answer)
    chain = _hit_chain()
    for s in sources:
        found = _source_lookup(s["source"])
        s["chunk_id"] = found.get("chunk_id", "")
        s["excerpt"] = found.get("excerpt")
        s["hit_chain"] = list(chain)
    return sources


def chat_with_rag(query: str, session_id: str | None) -> tuple[str, str, float]:
    t0 = time.time()
    session_id = session_id or allocate_session_id()
    with session_lock(session_id):
        messages = _build_messages(query, session_id)
        agent_messages = _maybe_compress_history(messages)
        print(f"  [计时] 加载会话历史: {time.time() - t0:.2f}s")

        t1 = time.time()
        agent = _get_agent()
        print(f"  [计时] 获取/构建 RAG Agent: {time.time() - t1:.2f}s")

        t2 = time.time()
        answer_parts = []
        for chunk in stream_rag_response(agent, agent_messages):
            if chunk:
                answer_parts.append(chunk)
        answer = "".join(answer_parts)
        print(f"  [计时] Agent 流式回答: {time.time() - t2:.2f}s")

        history = _serialize_messages(messages) + [{"role": "assistant", "content": answer}]
        t3 = time.time()
        new_session_id = save_history(history, session_id)
        print(f"  [计时] 保存会话历史: {time.time() - t3:.2f}s")

    elapsed_ms = (time.time() - t0) * 1000
    print(f"  [计时] chat_with_rag 总计: {elapsed_ms / 1000:.2f}s")
    return answer, new_session_id, round(elapsed_ms, 2)


def stream_chat_events(
    query: str,
    session_id: str | None,
    stop_event,
) -> Iterator[dict]:
    """Yield chat stream events; persist history (including interrupted runs).

    Event types: message_start, token, tool, sources, message_end.

    ``tool`` is emitted only when the agent called at least one tool, with
    the ordered list of tool names; it is a lightweight trace intended for
    developer mode and carries no prompt or raw chunk data.

    ``stop_event`` is a threading.Event the caller can set to stop token
    generation. Whatever text was already produced is persisted as an
    assistant message with ``interrupted=True``.

    For brand-new sessions the session id is pre-allocated up front and
    carried by ``message_start``, so an interrupted run remains
    recoverable on the client even if the connection dies before
    ``message_end``.
    """
    if session_id is None:
        session_id = allocate_session_id()
    with session_lock(session_id):
        yield {"type": "message_start", "data": {"session_id": session_id}}
        t0 = time.time()

        messages = _build_messages(query, session_id)
        agent_messages = _maybe_compress_history(messages)
        agent = _get_agent()

        tool_names: list[str] = []

        def _on_tool(name: str) -> None:
            if name not in tool_names:
                tool_names.append(name)

        answer_parts = []
        failed = False
        new_session_id = session_id
        try:
            for chunk in stream_rag_response(agent, agent_messages, on_tool=_on_tool):
                if stop_event.is_set():
                    break
                if chunk:
                    answer_parts.append(chunk)
                    yield {"type": "token", "data": {"text": chunk}}
        except Exception:
            failed = True
            raise
        finally:
            answer = "".join(answer_parts)
            interrupted = stop_event.is_set() or failed
            history = _serialize_messages(messages) + [
                {"role": "assistant", "content": answer, "interrupted": interrupted}
            ]
            new_session_id = save_history(history, session_id)

        if tool_names:
            yield {"type": "tool", "data": {"tools": tool_names}}
        elapsed_ms = (time.time() - t0) * 1000

        yield {"type": "sources", "data": {"sources": build_sources(answer)}}
        yield {
            "type": "message_end",
            "data": {
                "session_id": new_session_id,
                "elapsed_ms": round(elapsed_ms, 2),
                "interrupted": interrupted,
            },
        }
