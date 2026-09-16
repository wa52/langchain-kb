import asyncio
import uuid
from datetime import datetime, timezone
from threading import Lock


class IndexTaskManager:
    def __init__(self):
        self._tasks: dict[str, dict] = {}
        self._lock = Lock()

    def create_task(self, path: str) -> str:
        with self._lock:
            for t in self._tasks.values():
                if t["path"] == path and t["status"] in ("pending", "running"):
                    raise ValueError(f"Task already exists for path: {path}")
            task_id = str(uuid.uuid4())
            self._tasks[task_id] = {
                "task_id": task_id,
                "status": "pending",
                "path": path,
                "progress": None,
                "result": None,
                "error": None,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            self._prune_finished()
            return task_id

    def _prune_finished(self, keep: int = 200):
        finished = [t for t in self._tasks.values() if t["status"] not in ("pending", "running")]
        for task in sorted(finished, key=lambda t: t["created_at"])[:-keep]:
            self._tasks.pop(task["task_id"], None)

    def get_task(self, task_id: str) -> dict | None:
        with self._lock:
            task = self._tasks.get(task_id)
            return dict(task) if task else None

    def update_task(self, task_id: str, **kwargs):
        with self._lock:
            if task_id in self._tasks:
                self._tasks[task_id].update(kwargs)

    def has_active_task(self, path: str) -> bool:
        with self._lock:
            return any(
                t["path"] == path and t["status"] in ("pending", "running")
                for t in self._tasks.values()
            )

    def latest_task(self) -> dict | None:
        with self._lock:
            if not self._tasks:
                return None
            return dict(max(self._tasks.values(), key=lambda t: t["created_at"]))

    def clear(self) -> None:
        """Drop all tracked tasks (used by tests for isolation)."""
        with self._lock:
            self._tasks.clear()


_task_manager = IndexTaskManager()


def get_task_manager() -> IndexTaskManager:
    return _task_manager


async def run_index_task(task_id: str, path: str, in_place: bool = False, exclude: list[str] | None = None):
    mgr = get_task_manager()
    from src.status import get_registry
    reg = get_registry()
    mgr.update_task(task_id, status="running", progress="Starting...")
    reg.set_loading("index", f"索引任务 {task_id}")
    try:
        from pathlib import Path
        path_obj = Path(path)

        def _do_index():
            if in_place:
                mgr.update_task(task_id, progress="Indexing...")
                from src.ingestion.pipeline import run_single_file_update
                count = run_single_file_update(path)
            elif path_obj.exists():
                mgr.update_task(task_id, progress="Indexing...")
                from config import EXTERNAL_DIR
                from src.ingestion.pipeline import run_add_path
                count = run_add_path(path, EXTERNAL_DIR, exclude=exclude)
            else:
                mgr.update_task(task_id, progress="Full ingestion...")
                from config import DATA_DIR
                from src.ingestion.pipeline import run_ingestion
                count = run_ingestion(DATA_DIR)
            from src.resources import ResourceManager
            rm = ResourceManager.get_instance()
            rm.invalidate_retriever_cache()
            return count

        loop = asyncio.get_event_loop()
        count = await loop.run_in_executor(None, _do_index)
        mgr.update_task(
            task_id,
            status="done",
            progress="Complete",
            result={"chunks_added": count},
        )
        reg.set_ready("index", f"索引任务 {task_id} · {count} chunks")
    except Exception as e:
        mgr.update_task(
            task_id,
            status="failed",
            error=str(e),
        )
        reg.set_error("index", e, f"索引任务 {task_id}")


async def run_remove_task(task_id: str, name: str, keep_file: bool = False):
    mgr = get_task_manager()
    from src.status import get_registry
    reg = get_registry()
    mgr.update_task(task_id, status="running", progress="Removing...")
    reg.set_loading("index", f"移除任务 {task_id}")
    try:

        def _do_remove():
            from src.api.services.files import remove_file
            return remove_file(name, keep_file, echo_fn=lambda *a, **k: None)

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, _do_remove)
        mgr.update_task(
            task_id,
            status="done",
            progress="Complete",
            result=result,
        )
        reg.set_ready("index", f"移除任务 {task_id} · {name}")
    except Exception as e:
        mgr.update_task(
            task_id,
            status="failed",
            error=str(e),
        )
        reg.set_error("index", e, f"移除任务 {task_id}")
