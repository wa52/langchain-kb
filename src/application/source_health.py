"""Read-only health checks for already tracked knowledge sources."""

from collections import defaultdict
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any


class SourceHealthAuditor:
    """Compare tracked fingerprints with files under explicitly configured roots.

    The source list, root mapping, and file hasher are injected at the
    composition boundary so the application use case does not depend on the
    legacy tracker or filesystem adapter.
    """

    def __init__(
        self,
        *,
        list_sources: Callable[[], Iterable[dict[str, Any]]],
        source_roots: dict[str, Path],
        hash_file: Callable[[Path], str],
    ) -> None:
        self._list_sources = list_sources
        self._source_roots = source_roots
        self._hash_file = hash_file

    def run(self, *, progress: Callable[[int, int], None] | None = None) -> dict[str, Any]:
        records = list(self._list_sources())
        total = len(records)
        inspected: list[dict[str, Any]] = []
        current_hashes: dict[str, list[int]] = defaultdict(list)

        for index, record in enumerate(records, start=1):
            source_type = str(record.get("source_type", ""))
            raw_key = str(record.get("file_key", ""))
            item: dict[str, Any] = {
                "source_type": source_type,
                "file_key": _display_key(raw_key),
                "status": "unresolved",
                "duplicate_count": 0,
            }
            root = self._source_roots.get(source_type)
            if root is None:
                item["status"] = "unresolved"
            else:
                item["status"], digest = self._inspect_one(root, raw_key, record.get("hash"))
                if digest:
                    current_hashes[digest].append(len(inspected))
                    item["_current_hash"] = digest
            inspected.append(item)
            if progress is not None:
                progress(index, total)

        duplicate_files = 0
        for matching_indices in current_hashes.values():
            if len(matching_indices) < 2:
                continue
            duplicate_files += len(matching_indices)
            for item_index in matching_indices:
                inspected[item_index]["duplicate_count"] = len(matching_indices) - 1
                if inspected[item_index]["status"] == "healthy":
                    inspected[item_index]["status"] = "duplicate"

        for item in inspected:
            item.pop("_current_hash", None)

        counts = defaultdict(int)
        for item in inspected:
            counts[item["status"]] += 1
        public_issues = [item for item in inspected if item["status"] != "healthy"]
        summary = {
            "total": total,
            "checked": total,
            "healthy": counts["healthy"],
            "missing": counts["missing"],
            "changed": counts["changed"],
            "duplicate_files": duplicate_files,
            "unreadable": counts["unreadable"],
            "unresolved": counts["unresolved"],
            "issues_total": len(public_issues),
        }
        return {
            "summary": summary,
            "issues": public_issues[:500],
            "issues_truncated": len(public_issues) > 500,
        }

    def _inspect_one(self, root: Path, raw_key: str, expected_hash: Any) -> tuple[str, str | None]:
        try:
            resolved_root = Path(root).expanduser().resolve(strict=True)
        except FileNotFoundError:
            return "missing", None
        except (OSError, RuntimeError):
            return "unreadable", None

        try:
            supplied = Path(raw_key).expanduser()
            candidate = supplied if supplied.is_absolute() else resolved_root / supplied
            resolved_file = candidate.resolve(strict=True)
        except FileNotFoundError:
            return "missing", None
        except (OSError, RuntimeError, ValueError):
            return "unreadable", None

        try:
            resolved_file.relative_to(resolved_root)
        except ValueError:
            return "unresolved", None
        if not resolved_file.is_file():
            return "missing", None
        try:
            digest = self._hash_file(resolved_file)
        except (OSError, PermissionError):
            return "unreadable", None
        if not isinstance(expected_hash, str) or digest != expected_hash:
            return "changed", digest
        return "healthy", digest


def _display_key(raw_key: str) -> str:
    """Expose a relative label only; legacy absolute keys are basename-only."""
    path = Path(raw_key)
    if path.is_absolute() or ".." in path.parts:
        return path.name or "[invalid path]"
    return path.as_posix()
