import time

from src.agent.rag_agent import create_rag_agent, stream_rag_response
from src.agent.chat_history import save_history, load_history


def _get_agent():
    """Return the RAG agent, reused across requests via ResourceManager.
    Keeps a module-level reference to create_rag_agent so tests can patch it."""
    from src.resources import ResourceManager
    try:
        rm = ResourceManager.get_instance()
        if rm.is_ready() and rm.agent is not None:
            return rm.agent
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


def chat_with_rag(query: str, session_id: str | None) -> tuple[str, str, float]:
    t0 = time.time()
    if session_id:
        saved = load_history(session_id)
        messages = (saved or []) + [{"role": "user", "content": query}]
    else:
        messages = [{"role": "user", "content": query}]
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

    serializable = []
    for m in messages:
        if isinstance(m, dict):
            serializable.append(m)
        else:
            serializable.append({
                "role": getattr(m, "type", getattr(m, "role", "")),
                "content": getattr(m, "content", ""),
            })
    history = serializable + [{"role": "assistant", "content": answer}]
    t3 = time.time()
    new_session_id = save_history(history, session_id)
    print(f"  [计时] 保存会话历史: {time.time() - t3:.2f}s")

    elapsed_ms = (time.time() - t0) * 1000
    print(f"  [计时] chat_with_rag 总计: {elapsed_ms / 1000:.2f}s")
    return answer, new_session_id, round(elapsed_ms, 2)
