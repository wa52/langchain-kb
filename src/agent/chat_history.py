import json
from datetime import datetime
from pathlib import Path

HISTORY_DIR = Path("./data/chat_history")


def _ensure_dir():
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)


def _session_path(session_id: str | None = None) -> Path:
    _ensure_dir()
    if session_id:
        return HISTORY_DIR / f"{session_id}.json"
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return HISTORY_DIR / f"session_{ts}.json"


def save_history(messages: list[dict], session_id: str | None = None):
    path = _session_path(session_id)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(messages, f, ensure_ascii=False, indent=2)
    return path.stem


def load_history(session_id: str) -> list[dict] | None:
    path = HISTORY_DIR / f"{session_id}.json"
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def compress_history(messages: list[dict], llm, keep_rounds: int = 10) -> list[dict]:
    user_turns = [m for m in messages if m["role"] == "user"]
    if len(user_turns) <= keep_rounds:
        return messages
    cut = keep_rounds * 2
    old_part = messages[:-cut]
    recent_part = messages[-cut:]
    prompt = (
        "将以下对话历史压缩成一段概括（中文，50字以内），"
        "保留关键事实、决定和约定，丢弃细节。\n\n"
        + "\n".join(
            f"{'用户' if m['role'] == 'user' else '助手'}: {m['content'][:200]}"
            for m in old_part
        )
    )
    try:
        summary = llm.invoke(prompt).content.strip()
    except Exception:
        summary = f"共 {len(old_part)//2} 轮对话历史"
    return [{"role": "system", "content": f"[历史摘要] {summary}"}] + recent_part


def list_sessions() -> list[dict]:
    _ensure_dir()
    sessions = []
    for p in sorted(HISTORY_DIR.glob("*.json"), reverse=True):
        sessions.append({
            "id": p.stem,
            "created": datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M"),
            "size": p.stat().st_size,
        })
    return sessions
