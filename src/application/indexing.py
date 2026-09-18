"""Document indexing use-case facade."""

from src.adapters.legacy.indexing import get_task_manager, run_index_task, run_remove_task

__all__ = ["get_task_manager", "run_index_task", "run_remove_task"]
