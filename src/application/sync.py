"""Application facade for scheduled synchronization operations."""

from src.adapters.legacy import sync as _sync

get_sync_view = _sync.get_sync_view
add_sync_dir = _sync.add_sync_dir
remove_sync_dir = _sync.remove_sync_dir
run_sync_now = _sync.run_sync_now

__all__ = ["get_sync_view", "add_sync_dir", "remove_sync_dir", "run_sync_now"]
