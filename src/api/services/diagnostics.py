"""Full diagnostics task management for the web client.

Full diagnostics run only on explicit user request (POST /api/v1/diagnostics).
Probes reuse ``src.monitor.run_checks`` (read-only); a single failed check can
be repaired on demand via ``src.monitor.repair`` after the user confirms.
"""

import asyncio
import uuid
from datetime import datetime, timezone


class DiagnosticsTaskManager:
    def __init__(self):
        self._tasks: dict[str, dict] = {}

    def create_task(self) -> str:
        task_id = str(uuid.uuid4())
        self._tasks[task_id] = {
            "task_id": task_id,
            "status": "pending",
            "result": None,
            "error": None,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        return task_id

    def get_task(self, task_id: str) -> dict | None:
        return self._tasks.get(task_id)

    def update_task(self, task_id: str, **kwargs):
        if task_id in self._tasks:
            self._tasks[task_id].update(kwargs)

    def has_active(self) -> bool:
        return any(
            t["status"] in ("pending", "running") for t in self._tasks.values()
        )

    def clear(self) -> None:
        self._tasks.clear()


_task_manager = DiagnosticsTaskManager()


def get_diagnostics_task_manager() -> DiagnosticsTaskManager:
    return _task_manager


def _silent(*args, **kwargs):
    """No-op echo for monitor probes in the API context (no stdout spam)."""


async def run_diagnostics_task(task_id: str):
    mgr = get_diagnostics_task_manager()
    mgr.update_task(task_id, status="running")
    try:
        def _run():
            from src.monitor import run_checks
            return run_checks(echo_fn=_silent)

        loop = asyncio.get_running_loop()
        checks = await loop.run_in_executor(None, _run)
        failed = [c for c in checks if not c.get("ok")]
        mgr.update_task(
            task_id,
            status="done",
            result={
                "checks": checks,
                "summary": {
                    "total": len(checks),
                    "ok": len(checks) - len(failed),
                    "failed": len(failed),
                },
            },
        )
    except Exception as e:
        mgr.update_task(task_id, status="failed", error=str(e))


async def repair_check(name: str) -> bool:
    def _repair():
        from src.monitor import repair
        try:
            return repair(name, echo_fn=_silent)
        except Exception:
            return False

    loop = asyncio.get_running_loop()
    return bool(await loop.run_in_executor(None, _repair))
