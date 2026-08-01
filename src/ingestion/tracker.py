import json
import hashlib
import os
from pathlib import Path

from config import KNOWLEDGE_HOME

TRACKER_FILE = os.getenv(
    "FILE_TRACKER_PATH", str(KNOWLEDGE_HOME / "data" / "file_tracker.json")
)


def _load_tracker() -> dict:
    path = Path(TRACKER_FILE)
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"internal": {}, "external": {}}


def _save_tracker(tracker: dict):
    path = Path(TRACKER_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(tracker, f, ensure_ascii=False, indent=2)


def get_file_hash(filepath: str) -> str:
    stat = Path(filepath).stat()
    return hashlib.md5(f"{stat.st_mtime}_{stat.st_size}".encode()).hexdigest()


def get_changed_files(data_dirs_with_type: list[tuple[str, str]]) -> tuple[list[str], list[str]]:
    tracker = _load_tracker()
    changed = []
    unchanged = []

    for data_dir_str, source_type in data_dirs_with_type:
        data_dir = Path(data_dir_str)
        if not data_dir.exists():
            continue
        for path in data_dir.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in (".md", ".txt", ".pdf"):
                continue
            try:
                file_key = str(path.relative_to(data_dir))
            except ValueError:
                file_key = str(path)
            registry = tracker.get(source_type, {})
            current_hash = get_file_hash(str(path))
            stored_hash = registry.get(file_key)
            if stored_hash != current_hash:
                changed.append(str(path))
            else:
                unchanged.append(str(path))

    return changed, unchanged


def update_tracker(source_type: str, base_dir: str | Path, filepaths: list[str] | None = None):
    base_dir = Path(base_dir)
    tracker = _load_tracker()
    registry = tracker.setdefault(source_type, {})

    if filepaths:
        for fp in filepaths:
            try:
                file_key = Path(fp).relative_to(base_dir)
            except ValueError:
                file_key = Path(fp).name
            registry[str(file_key)] = get_file_hash(fp)
    else:
        for path in base_dir.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in (".md", ".txt", ".pdf"):
                continue
            try:
                file_key = str(path.relative_to(base_dir))
            except ValueError:
                file_key = path.name
            registry[file_key] = get_file_hash(str(path))

    _save_tracker(tracker)


def remove_from_tracker(source_name: str, source_type: str | None = None):
    tracker = _load_tracker()
    types = [source_type] if source_type else ("internal", "external")
    for st in types:
        registry = tracker.get(st, {})
        to_delete = [k for k in registry if Path(k).name == source_name or k == source_name]
        for k in to_delete:
            del registry[k]
    _save_tracker(tracker)


def list_all_files() -> list[dict]:
    tracker = _load_tracker()
    result = []
    for source_type in ("internal", "external"):
        registry = tracker.get(source_type, {})
        for file_key, file_hash in registry.items():
            result.append({"source_type": source_type, "file_key": file_key, "hash": file_hash})
    return result
