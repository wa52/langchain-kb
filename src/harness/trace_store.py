"""Non-blocking in-process storage for completed Agent traces."""

from threading import Lock
from typing import Any


class TraceStore:
    def __init__(self, max_runs: int = 256) -> None:
        self._items: dict[str, dict[str, Any]] = {}
        self._lock = Lock()
        self._max_runs = max_runs

    def put(self, trace: Any) -> None:
        snapshot = trace.snapshot()
        with self._lock:
            self._items[str(snapshot["run_id"])] = snapshot
            while len(self._items) > self._max_runs:
                self._items.pop(next(iter(self._items)))

    def get(self, run_id: str) -> dict[str, Any] | None:
        with self._lock:
            value = self._items.get(run_id)
            return dict(value) if value is not None else None


trace_store = TraceStore()
