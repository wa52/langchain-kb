"""File-management service: list tracked KB files and remove one from the index.

The read path mirrors the CLI ``knowledge files`` (tracker-based); removal
reuses the ingestion pipeline's ``run_remove`` so chunks, the on-disk copy and
the BM25 index stay consistent.
"""


def list_files_view() -> dict:
    from src.ingestion.tracker import list_all_files
    files = list_all_files()
    return {"files": files, "total": len(files)}


def remove_file(name: str, keep_file: bool = False, echo_fn=print) -> dict:
    from config import EXTERNAL_DIR
    from src.ingestion.pipeline import run_remove
    run_remove(name, EXTERNAL_DIR, keep_file=keep_file, echo_fn=echo_fn)
    return {"removed": name, "keep_file": keep_file}
