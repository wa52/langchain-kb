def _module():
    from src.api.services import sync
    return sync


def get_sync_view(): return _module().get_sync_view()
def add_sync_dir(path: str): return _module().add_sync_dir(path)
def remove_sync_dir(path: str): return _module().remove_sync_dir(path)
async def run_sync_now(): return await _module().run_sync_now()
