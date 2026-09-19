"""Side-channel timing records for knowledge retrieval."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import Lock
from typing import Any
from uuid import uuid4


@dataclass
class RetrievalRecord:
    """A compact, framework-neutral snapshot of one retrieval attempt."""

    record_id: str = field(default_factory=lambda: uuid4().hex)
    query: str = ""
    capability: str | None = None
    index_version: int = 0
    cache_hit: bool = False
    status: str = "running"
    started_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    elapsed_ms: float | None = None
    stages: dict[str, float] = field(default_factory=dict)
    raw_docs_count: int = 0
    selected_docs_count: int = 0
    flags: dict[str, bool] = field(default_factory=dict)
    error: str | None = None

    def finish(self, elapsed_ms: float, *, status: str = "completed") -> None:
        self.elapsed_ms = round(elapsed_ms, 2)
        self.status = status

    def snapshot(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "query": self.query,
            "capability": self.capability,
            "index_version": self.index_version,
            "cache_hit": self.cache_hit,
            "status": self.status,
            "started_at": self.started_at,
            "elapsed_ms": self.elapsed_ms,
            "stages": dict(self.stages),
            "raw_docs_count": self.raw_docs_count,
            "selected_docs_count": self.selected_docs_count,
            "flags": dict(self.flags),
            "error": self.error,
        }


class RetrievalRecordStore:
    """Bounded, in-memory store; recording never performs filesystem or I/O work."""

    def __init__(self, max_records: int = 256) -> None:
        self._items: dict[str, dict[str, Any]] = {}
        self._max_records = max(1, max_records)
        self._lock = Lock()

    def put(self, record: RetrievalRecord) -> None:
        snapshot = record.snapshot()
        with self._lock:
            self._items[record.record_id] = snapshot
            while len(self._items) > self._max_records:
                self._items.pop(next(iter(self._items)))

    def get(self, record_id: str) -> dict[str, Any] | None:
        with self._lock:
            value = self._items.get(record_id)
            return dict(value) if value is not None else None

    def recent(self, limit: int = 50) -> list[dict[str, Any]]:
        limit = max(1, min(limit, self._max_records))
        with self._lock:
            values = list(self._items.values())[-limit:]
            return [dict(value) for value in reversed(values)]

    def clear(self) -> None:
        with self._lock:
            self._items.clear()


retrieval_record_store = RetrievalRecordStore()
