import json
import os
import re
import tempfile
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from threading import Lock, RLock

from config import KNOWLEDGE_HOME

HISTORY_DIR = Path(
    os.getenv("CHAT_HISTORY_DIR", str(KNOWLEDGE_HOME / "data" / "chat_history"))
)
if not HISTORY_DIR.is_absolute():
    HISTORY_DIR = KNOWLEDGE_HOME / HISTORY_DIR

_SESSION_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")
_HISTORY_LOCK = Lock()
_SESSION_LOCKS_GUARD = Lock()
_SESSION_LOCKS: dict[str, RLock] = {}
_SESSION_LOCK_USERS: dict[str, int] = {}
_SESSION_FILE_LOCKS: dict[str, list] = {}  # session_id -> [fileobj, refcount]


def _ensure_dir():
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)


def _session_path(session_id: str | None = None) -> Path:
    _ensure_dir()
    if session_id:
        if not _SESSION_ID_RE.fullmatch(session_id):
            raise ValueError("非法会话 ID：只能包含字母、数字、下划线和短横线")
        return HISTORY_DIR / f"{session_id}.json"
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return HISTORY_DIR / f"session_{ts}.json"


def allocate_session_id() -> str:
    """Allocate a unique session id without creating a file yet.

    Streaming chat pre-allocates the id for brand-new sessions so the
    client can learn it from the first SSE event (``message_start``) and
    still reconcile an interrupted run even when the connection is aborted
    before ``message_end`` reaches it. Microsecond precision plus an
    existence-guarded ``_N`` suffix makes same-second collisions
    practically impossible even without an atomic file reservation."""
    _ensure_dir()
    base = datetime.now().strftime("session_%Y%m%d_%H%M%S_%f")
    candidate = base
    i = 1
    while (HISTORY_DIR / f"{candidate}.json").exists():
        candidate = f"{base}_{i}"
        i += 1
    return candidate


@contextmanager
def session_lock(session_id: str):
    """Serialize read-generate-write cycles for one session.

    Two layers: an in-process RLock (reentrant so nested save/load inside an
    outer lock never deadlocks) plus a per-session OS file lock that also
    serializes API / stdio MCP / CLI processes sharing the same history dir.
    The file lock is refcounted per session: the OS lock is taken once for
    the outermost holder and released when the last user leaves."""
    if not _SESSION_ID_RE.fullmatch(session_id):
        raise ValueError("非法会话 ID：只能包含字母、数字、下划线和短横线")
    with _SESSION_LOCKS_GUARD:
        lock = _SESSION_LOCKS.setdefault(session_id, RLock())
        _SESSION_LOCK_USERS[session_id] = _SESSION_LOCK_USERS.get(session_id, 0) + 1
    lock.acquire()
    file_lock = None
    try:
        with _SESSION_LOCKS_GUARD:
            entry = _SESSION_FILE_LOCKS.get(session_id)
            if entry is None:
                _ensure_dir()
                lock_path = HISTORY_DIR / f".{session_id}.lock"
                try:
                    fobj = open(lock_path, "a+b")
                except OSError:
                    fobj = None
                if fobj is not None:
                    try:
                        _acquire_os_lock(fobj)
                    except OSError:
                        fobj.close()
                        fobj = None
                    if fobj is not None:
                        entry = [fobj, 0]
                        _SESSION_FILE_LOCKS[session_id] = entry
            if entry is not None:
                entry[1] += 1
                file_lock = entry
        yield
    finally:
        if file_lock is not None:
            with _SESSION_LOCKS_GUARD:
                file_lock[1] -= 1
                if file_lock[1] == 0:
                    _SESSION_FILE_LOCKS.pop(session_id, None)
                    try:
                        _release_os_lock(file_lock[0])
                    finally:
                        file_lock[0].close()
        lock.release()
        with _SESSION_LOCKS_GUARD:
            remaining = _SESSION_LOCK_USERS[session_id] - 1
            if remaining == 0:
                _SESSION_LOCK_USERS.pop(session_id, None)
                if _SESSION_LOCKS.get(session_id) is lock:
                    _SESSION_LOCKS.pop(session_id, None)
            else:
                _SESSION_LOCK_USERS[session_id] = remaining


def _acquire_os_lock(fobj):
    """Non-blocking exclusive OS lock; retries briefly, then raises OSError."""
    import time

    deadline = time.monotonic() + 120.0
    while True:
        try:
            if os.name == "nt":
                import msvcrt
                fobj.seek(0)
                msvcrt.locking(fobj.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(fobj.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return
        except (OSError, BlockingIOError):
            if time.monotonic() >= deadline:
                raise
            time.sleep(0.05)


def _release_os_lock(fobj):
    if os.name == "nt":
        import msvcrt
        fobj.seek(0)
        msvcrt.locking(fobj.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl
        fcntl.flock(fobj.fileno(), fcntl.LOCK_UN)


def save_history(messages: list[dict], session_id: str | None = None):
    session_id = session_id or allocate_session_id()
    with session_lock(session_id), _HISTORY_LOCK:
        path = _session_path(session_id)
        fd, tmp_name = tempfile.mkstemp(prefix=f".{path.stem}.", suffix=".tmp", dir=path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(messages, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_name, path)
        finally:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)
    return path.stem


def load_history(session_id: str) -> list[dict] | None:
    with session_lock(session_id):
        path = _session_path(session_id)
        if not path.exists():
            return None
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)


def delete_history(session_id: str) -> bool:
    """Delete a saved session file. Returns True if it existed and was removed."""
    with session_lock(session_id), _HISTORY_LOCK:
        path = _session_path(session_id)
        if not path.exists():
            return False
        path.unlink()
        return True


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
