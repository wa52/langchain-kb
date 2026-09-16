"""Persist the Feishu open_id -> knowledge-base session_id mapping.

Each Feishu user keeps their own conversation history; sending `/new`
resets it. State is stored as JSON under <KNOWLEDGE_HOME>/data so it
survives bot restarts.
"""

import json
import os
import threading
from pathlib import Path

from config import KNOWLEDGE_HOME

DEFAULT_PATH = Path(
    os.getenv("FEISHU_SESSION_FILE", str(KNOWLEDGE_HOME / "data" / "feishu_sessions.json"))
)


class SessionStore:
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path else DEFAULT_PATH
        self._lock = threading.Lock()
        self._data: dict[str, dict] = {}
        self._load()

    def _load(self) -> None:
        try:
            if self.path.exists():
                raw = self.path.read_text(encoding="utf-8")
                self._data = json.loads(raw) if raw else {}
        except Exception:
            self._data = {}

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(tmp, self.path)

    def get(self, open_id: str) -> str | None:
        with self._lock:
            item = self._data.get(open_id)
            return item.get("session_id") if item else None

    def set(self, open_id: str, session_id: str) -> None:
        with self._lock:
            self._data[open_id] = {"session_id": session_id}
            self._save()

    def clear(self, open_id: str) -> bool:
        with self._lock:
            if open_id in self._data:
                del self._data[open_id]
                self._save()
                return True
            return False
