"""Document indexing use-case facade."""

from src.adapters.legacy.indexing import (
    get_task_manager, run_index_task, run_remove_task, run_tracked_reindex_task,
)

__all__ = ["get_task_manager", "run_index_task", "run_remove_task", "run_tracked_reindex_task"]
