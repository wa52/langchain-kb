"""File-management service: list tracked KB files and remove one from the index.

The read path mirrors the CLI ``knowledge files`` (tracker-based); removal
reuses the ingestion pipeline's ``run_remove`` so chunks, the on-disk copy and
the BM25 index stay consistent.
"""

from pathlib import Path

from src.ingestion.tracker import resolve_tracked_source


def list_files_view() -> dict:
    from src.ingestion.tracker import list_all_files
    files = list_all_files()
    return {"files": files, "total": len(files)}


def resolve_tracked_file(source_type: str, file_key: str) -> tuple[Path, Path]:
    """Resolve one tracked source under its configured root, without guessing names."""
    from config import DATA_DIR, EXTERNAL_DIR

    _, key = resolve_tracked_source(source_type, file_key)
    roots = {"internal": Path(DATA_DIR), "external": Path(EXTERNAL_DIR)}
    parts = key.split("/")

    root = roots[source_type].resolve(strict=True)
    path = (root / Path(*parts)).resolve(strict=True)
    if not path.is_relative_to(root) or not path.is_file():
        raise ValueError("来源文件不在配置目录内")
    return root, path


def remove_file(name: str, keep_file: bool = False, echo_fn=print) -> dict:
    from config import EXTERNAL_DIR
    from src.ingestion.pipeline import run_remove
    run_remove(name, EXTERNAL_DIR, keep_file=keep_file, echo_fn=echo_fn)
    return {"removed": name, "keep_file": keep_file}
