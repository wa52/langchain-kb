"""Explicit, asynchronous source-health audit tasks for the Web/API surface."""

import asyncio
from copy import deepcopy
from datetime import datetime, timezone
import logging
from threading import Lock
from uuid import uuid4


class SourceHealthTaskManager:
    def __init__(self) -> None:
        self._tasks: dict[str, dict] = {}
        self._lock = Lock()

    def create_task(self) -> str:
        with self._lock:
            if any(task["status"] in ("pending", "running") for task in self._tasks.values()):
                raise RuntimeError("知识源健康检查正在运行")
            task_id = uuid4().hex
            self._tasks[task_id] = {
                "task_id": task_id,
                "status": "pending",
                "progress": {"checked": 0, "total": 0},
                "result": None,
                "error": None,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            self._prune_finished()
            return task_id

    def update_task(self, task_id: str, **values) -> None:
        with self._lock:
            if task_id in self._tasks:
                self._tasks[task_id].update(values)

    def get_task(self, task_id: str) -> dict | None:
        with self._lock:
            task = self._tasks.get(task_id)
            return deepcopy(task) if task else None

    def has_active_task(self) -> bool:
        with self._lock:
            return any(task["status"] in ("pending", "running") for task in self._tasks.values())

    def _prune_finished(self, keep: int = 30) -> None:
        finished = [task for task in self._tasks.values() if task["status"] not in ("pending", "running")]
        for task in sorted(finished, key=lambda item: item["created_at"])[:-keep]:
            self._tasks.pop(task["task_id"], None)

    def clear(self) -> None:
        with self._lock:
            self._tasks.clear()


_task_manager = SourceHealthTaskManager()
logger = logging.getLogger(__name__)


def get_source_health_task_manager() -> SourceHealthTaskManager:
    return _task_manager


async def run_source_health_task(task_id: str) -> None:
    manager = get_source_health_task_manager()
    manager.update_task(task_id, status="running")
    try:
        def audit():
            from src.bootstrap.composition import create_source_health_auditor

            auditor = create_source_health_auditor()
            return auditor.run(
                progress=lambda checked, total: manager.update_task(
                    task_id,
                    progress={"checked": checked, "total": total},
                )
            )

        result = await asyncio.get_running_loop().run_in_executor(None, audit)
        manager.update_task(
            task_id,
            status="done",
            progress={"checked": result["summary"]["total"], "total": result["summary"]["total"]},
            result=result,
            completed_at=datetime.now(timezone.utc).isoformat(),
        )
    except Exception:
        logger.exception("Source health audit failed (task_id=%s)", task_id)
        manager.update_task(task_id, status="failed", error="知识源健康检查失败，请查看服务日志。")
