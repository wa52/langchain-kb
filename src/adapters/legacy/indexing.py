"""Compatibility adapter for the existing indexing task engine."""


def get_task_manager():
    from src.api.services.indexing import get_task_manager as _get
    return _get()


async def run_index_task(task_id: str, path: str, in_place: bool = False, exclude: list[str] | None = None):
    from src.api.services.indexing import run_index_task as _run
    return await _run(task_id, path, in_place=in_place, exclude=exclude)


async def run_remove_task(task_id: str, name: str, keep_file: bool = False):
    from src.api.services.indexing import run_remove_task as _run
    return await _run(task_id, name, keep_file=keep_file)
