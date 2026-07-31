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


_MAX_TITLE_LEN = 24


def _session_title(messages: list[dict]) -> str:
    if not messages:
        return "空会话"
    for msg in messages:
        if msg.get("role") == "user":
            content = msg.get("content") or ""
            title = content.strip().split("\n")[0].strip()
            if not title:
                return "空会话"
            if len(title) > _MAX_TITLE_LEN:
                truncated = title[:_MAX_TITLE_LEN - 1]
                title = truncated + "…"
            return title
    return "空会话"


def list_sessions() -> list[dict]:
    _ensure_dir()
    sessions = []
    for p in sorted(HISTORY_DIR.glob("*.json"), reverse=True):
        try:
            with open(p, "r", encoding="utf-8") as f:
                messages = json.load(f)
        except Exception:
            messages = []
        sessions.append({
            "id": p.stem,
            "created": datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M"),
            "size": p.stat().st_size,
            "title": _session_title(messages),
            "turns": len([m for m in messages if isinstance(m, dict) and m.get("role") == "user"]),
        })
    return sessions
