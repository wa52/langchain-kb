import time

from src.agent.rag_agent import create_rag_agent, stream_rag_response
from src.agent.chat_history import save_history, load_history


def chat_with_rag(query: str, session_id: str | None) -> tuple[str, str, float]:
    t0 = time.time()
    if session_id:
        saved = load_history(session_id)
        messages = (saved or []) + [{"role": "user", "content": query}]
    else:
        messages = [{"role": "user", "content": query}]

    agent = create_rag_agent()
    answer_parts = []
    for chunk in stream_rag_response(agent, messages):
        if chunk:
            answer_parts.append(chunk)
    answer = "".join(answer_parts)

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
    new_session_id = save_history(history, session_id)
    elapsed_ms = (time.time() - t0) * 1000
    return answer, new_session_id, round(elapsed_ms, 2)
