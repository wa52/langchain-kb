import re
import time
from typing import Iterator

from src.agent.rag_agent import create_rag_agent, stream_rag_response
from src.agent.chat_history import save_history, load_history

_CITATION_PATTERN = re.compile(r"\[来源:\s*([^\]]+)\]")


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


def chat_with_rag(query: str, session_id: str | None) -> tuple[str, str, float]:
    t0 = time.time()
    messages = _build_messages(query, session_id)
    print(f"  [计时] 加载会话历史: {time.time() - t0:.2f}s")

    t1 = time.time()
    agent = _get_agent()
    print(f"  [计时] 获取/构建 RAG Agent: {time.time() - t1:.2f}s")

    t2 = time.time()
    answer_parts = []
    for chunk in stream_rag_response(agent, messages):
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

    Event types: message_start, token, sources, message_end.

    ``stop_event`` is a threading.Event the caller can set to stop token
    generation. Whatever text was already produced is persisted as an
    assistant message with ``interrupted=True``.
    """
    yield {"type": "message_start", "data": {"session_id": session_id}}
    t0 = time.time()

    messages = _build_messages(query, session_id)
    agent = _get_agent()

    answer_parts = []
    for chunk in stream_rag_response(agent, messages):
        if stop_event.is_set():
            break
        if chunk:
            answer_parts.append(chunk)
            yield {"type": "token", "data": {"text": chunk}}

    answer = "".join(answer_parts)
    interrupted = stop_event.is_set()

    history = _serialize_messages(messages) + [
        {"role": "assistant", "content": answer, "interrupted": interrupted}
    ]
    new_session_id = save_history(history, session_id)
    elapsed_ms = (time.time() - t0) * 1000

    yield {"type": "sources", "data": {"sources": extract_sources(answer)}}
    yield {
        "type": "message_end",
        "data": {
            "session_id": new_session_id,
            "elapsed_ms": round(elapsed_ms, 2),
            "interrupted": interrupted,
        },
    }
