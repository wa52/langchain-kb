"""Scheduled experience-library sync.

Manages the curated ``EXPERIENCE_DIRS`` (server-local directories whose
markdown is indexed in place) plus the periodic sync cadence. Directory list
is persisted to ``.env`` (EXPERIENCE_DIRS); sync state (last run / result /
running) is persisted to ``<KNOWLEDGE_HOME>/data/sync_status.json``.
"""

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

import config

_STATUS_PATH = Path(config.KNOWLEDGE_HOME) / "data" / "sync_status.json"
_lock = threading.Lock()
_running = False


def _load_status() -> dict:
    try:
        if _STATUS_PATH.exists():
            return json.loads(_STATUS_PATH.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {"last_sync_at": None, "last_result": None}


def _save_status(status: dict):
    try:
        _STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
        _STATUS_PATH.write_text(
            json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception:
        pass


def _persist_dirs(dirs: list[str]):
    from dotenv import set_key

    value = ";".join(dirs)
    dotenv_path = Path(config.KNOWLEDGE_HOME) / ".env"
    dotenv_path.parent.mkdir(parents=True, exist_ok=True)
    dotenv_path.touch(exist_ok=True)
    set_key(str(dotenv_path), "EXPERIENCE_DIRS", value)
    os.environ["EXPERIENCE_DIRS"] = value
    config.EXPERIENCE_DIRS = list(dirs)


def get_sync_view() -> dict:
    status = _load_status()
    return {
        "dirs": list(config.EXPERIENCE_DIRS),
        "enabled": bool(config.EXPERIENCE_DIRS),
        "interval_hours": config.SYNC_INTERVAL_HOURS,
        "running": _running,
        "last_sync_at": status.get("last_sync_at"),
        "last_result": status.get("last_result"),
    }


def add_sync_dir(path: str) -> dict:
    """Add a server-local directory to the scheduled experience sources."""
    resolved = str(Path(path).expanduser().resolve())
    if not Path(resolved).is_dir():
        raise ValueError(f"目录不存在: {path}")
    dirs = [d for d in config.EXPERIENCE_DIRS if Path(d).resolve() != Path(resolved)]
    dirs.append(resolved)
    _persist_dirs(dirs)
    return {"dirs": list(config.EXPERIENCE_DIRS), "path": resolved}


def remove_sync_dir(path: str) -> dict:
    """Remove a directory from the scheduled experience sources."""
    resolved = str(Path(path).expanduser().resolve())
    dirs = [d for d in config.EXPERIENCE_DIRS if Path(d).resolve() != Path(resolved)]
    _persist_dirs(dirs)
    return {"dirs": list(config.EXPERIENCE_DIRS)}


def _claim() -> bool:
    global _running
    with _lock:
        if _running:
            return False
        _running = True
    return True


def _run_sync() -> dict:
    """Run sync_experience and persist the outcome. Caller must have claimed."""
    global _running
    try:
        from src.ingestion.pipeline import sync_experience
        result = sync_experience(echo_fn=print)
        status = _load_status()
        status["last_sync_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        status["last_result"] = result
        _save_status(status)
        return result
    finally:
        status = _load_status()
        status["running"] = False
        _save_status(status)
        with _lock:
            _running = False


async def run_sync_now() -> bool:
    """Start a sync on the event-loop executor; returns True if it was started."""
    import asyncio
    if not _claim():
        return False
    loop = asyncio.get_running_loop()
    loop.run_in_executor(None, _run_sync)
    return True


def _due() -> bool:
    if not config.EXPERIENCE_DIRS:
        return False
    status = _load_status()
    last = status.get("last_sync_at")
    if not last:
        return True
    try:
        dt = datetime.fromisoformat(last)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        elapsed_h = (datetime.now(timezone.utc) - dt).total_seconds() / 3600
        return elapsed_h >= config.SYNC_INTERVAL_HOURS
    except Exception:
        return True


async def maybe_run_scheduled() -> bool:
    """Start a sync when one is due; returns True if a sync was started."""
    if _running or not _due():
        return False
    return await run_sync_now()


async def sync_loop():
    """Background loop: check the sync cadence every minute until shutdown."""
    import asyncio
    from src.resources import ResourceManager
    rm = ResourceManager.get_instance()
    while not rm._shutdown_event.is_set():
        try:
            await maybe_run_scheduled()
        except Exception:
            pass
        try:
            await asyncio.wait_for(rm._shutdown_event.wait(), timeout=60)
        except TimeoutError:
            continue
