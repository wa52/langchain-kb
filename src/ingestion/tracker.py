import json
import copy
import hashlib
import os
import tempfile
from pathlib import Path
from threading import RLock

from config import KNOWLEDGE_HOME
from src.ingestion.loader import _ALL_EXTS

TRACKER_FILE = os.getenv(
    "FILE_TRACKER_PATH", str(KNOWLEDGE_HOME / "data" / "file_tracker.json")
)
if not Path(TRACKER_FILE).is_absolute():
    TRACKER_FILE = str(KNOWLEDGE_HOME / TRACKER_FILE)
_TRACKER_LOCK = RLock()


def snapshot_tracker() -> dict:
    """Deep copy of the current tracker state (for transactional restore)."""
    with _TRACKER_LOCK:
        return copy.deepcopy(_load_tracker())


def restore_tracker(snapshot: dict):
    """Restore the tracker to a snapshot taken by ``snapshot_tracker``."""
    with _TRACKER_LOCK:
        _save_tracker(snapshot)


def _load_tracker() -> dict:
    path = Path(TRACKER_FILE)
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"internal": {}, "external": {}}


def _save_tracker(tracker: dict):
    path = Path(TRACKER_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(tracker, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def get_file_hash(filepath: str) -> str:
    digest = hashlib.sha256()
    with open(filepath, "rb") as f:
        for block in iter(lambda: f.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def get_changed_files(data_dirs_with_type: list[tuple[str, str]]) -> tuple[list[str], list[str]]:
    tracker = _load_tracker()
    changed = []
    unchanged = []

    for data_dir_str, source_type in data_dirs_with_type:
        data_dir = Path(data_dir_str)
        if not data_dir.exists():
            continue
        for path in data_dir.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in _ALL_EXTS:
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
    with _TRACKER_LOCK:
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
                if not path.is_file() or path.suffix.lower() not in _ALL_EXTS:
                    continue
                try:
                    file_key = str(path.relative_to(base_dir))
                except ValueError:
                    file_key = path.name
                registry[file_key] = get_file_hash(str(path))

        _save_tracker(tracker)


def remove_from_tracker(source_name: str, source_type: str | None = None):
    with _TRACKER_LOCK:
        tracker = _load_tracker()
        types = [source_type] if source_type else ("internal", "external")
        for st in types:
            registry = tracker.get(st, {})
            to_delete = [k for k in registry if Path(k).name == source_name or k == source_name]
            for k in to_delete:
                del registry[k]
        _save_tracker(tracker)


def is_already_indexed(filepaths: list[str], source_type: str = "external") -> bool:
    """Return True if every file already has a matching content hash recorded in
    the tracker (i.e. it was ingested before). Used to skip duplicate ingests."""
    if not filepaths:
        return False
    tracker = _load_tracker()
    registry = tracker.get(source_type, {})
    for fp in filepaths:
        key = Path(fp).name
        current = get_file_hash(fp)
        stored = None
        for k, h in registry.items():
            if Path(k).name == key and h == current:
                stored = h
                break
        if stored is None:
            return False
    return True


def list_all_files() -> list[dict]:
    tracker = _load_tracker()
    result = []
    for source_type, registry in tracker.items():
        for file_key, file_hash in registry.items():
            result.append({"source_type": source_type, "file_key": file_key, "hash": file_hash})
    return result


def get_indexed_hashes() -> set[str]:
    """Return all content hashes already recorded by any knowledge source."""
    with _TRACKER_LOCK:
        tracker = _load_tracker()
        return {
            digest
            for registry in tracker.values()
            if isinstance(registry, dict)
            for digest in registry.values()
            if isinstance(digest, str) and digest
        }
