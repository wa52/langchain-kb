import asyncio
import uuid
from datetime import datetime, timezone


class IndexTaskManager:
    def __init__(self):
        self._tasks: dict[str, dict] = {}

    def create_task(self, path: str) -> str:
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
        return task_id

    def get_task(self, task_id: str) -> dict | None:
        return self._tasks.get(task_id)

    def update_task(self, task_id: str, **kwargs):
        if task_id in self._tasks:
            self._tasks[task_id].update(kwargs)

    def has_active_task(self, path: str) -> bool:
        return any(
            t["path"] == path and t["status"] in ("pending", "running")
            for t in self._tasks.values()
        )


_task_manager = IndexTaskManager()


def get_task_manager() -> IndexTaskManager:
    return _task_manager


async def run_index_task(task_id: str, path: str):
    mgr = get_task_manager()
    mgr.update_task(task_id, status="running", progress="Starting...")
    try:
        from config import DATA_DIR, EXTERNAL_DIR
        from src.ingestion.pipeline import run_add_path, run_ingestion
        from pathlib import Path

        path_obj = Path(path)
        if path_obj.exists():
            def _do_index():
                mgr.update_task(task_id, progress="Indexing...")
                count = run_add_path(str(path_obj), EXTERNAL_DIR)
                from src.resources import ResourceManager
                rm = ResourceManager.get_instance()
                rm.invalidate_retriever_cache()
                return count
            loop = asyncio.get_event_loop()
            count = await loop.run_in_executor(None, _do_index)
        else:
            def _do_full_ingest():
                mgr.update_task(task_id, progress="Full ingestion...")
                count = run_ingestion(DATA_DIR)
                from src.resources import ResourceManager
                rm = ResourceManager.get_instance()
                rm.invalidate_retriever_cache()
                return count
            loop = asyncio.get_event_loop()
            count = await loop.run_in_executor(None, _do_full_ingest)

        mgr.update_task(
            task_id,
            status="done",
            progress="Complete",
            result={"chunks_added": count},
        )
    except Exception as e:
        mgr.update_task(
            task_id,
            status="failed",
            error=str(e),
        )
