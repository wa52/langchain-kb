"""Bounded local-file capabilities backed by the configured filesystem roots."""

import hashlib
import json
from pathlib import Path

from langchain_core.tools import tool

from src.agent.mcp_client import default_mcp_config_path, filesystem_allowed_roots
from src.ingestion.loader import _ALL_EXTS

_MAX_FILES = 10_000
_MAX_DUPLICATE_PAIRS = 200


def validate_filesystem_path(path: str, *, config_path=None) -> Path:
    """Resolve an existing path and ensure it stays inside an allowed root."""
    try:
        resolved = Path(path).expanduser().resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise ValueError(f"路径不存在或无法访问: {path}") from exc
    roots = filesystem_allowed_roots(config_path or default_mcp_config_path())
    for root in roots:
        try:
            resolved.relative_to(root)
            return resolved
        except ValueError:
            continue
    raise PermissionError(f"路径不在 filesystem MCP 授权目录内: {resolved}")


def _supported_files(root: Path) -> list[Path]:
    if root.is_file():
        return [root] if root.suffix.lower() in _ALL_EXTS else []
    files = []
    for candidate in root.rglob("*"):
        if not candidate.is_file() or candidate.suffix.lower() not in _ALL_EXTS:
            continue
        # Resolve each candidate too: a symlink under an allowed folder must not
        # be a path traversal escape.
        resolved = candidate.resolve(strict=True)
        if not _is_within(resolved, root):
            continue
        files.append(resolved)
        if len(files) > _MAX_FILES:
            raise ValueError(f"目录包含超过 {_MAX_FILES} 个受支持文件，请缩小范围")
    return files


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def _inventory(path: Path) -> tuple[list[Path], dict[str, list[str]]]:
    files = _supported_files(path)
    # Group by size first to avoid hashing unlike files; contents are never
    # returned to the model or user.
    by_size: dict[int, dict[str, list[str]]] = {}
    for file in files:
        relative = file.name if path.is_file() else file.relative_to(path).as_posix()
        by_size.setdefault(file.stat().st_size, {}).setdefault(_digest(file), []).append(relative)
    return files, {
        digest: paths
        for same_size in by_size.values()
        for digest, paths in same_size.items()
    }


@tool
def inspect_local_path(path: str, compare_with: str = "") -> str:
    """检查授权目录中的文档清单；可比较两个路径的相同内容文件，不读取或返回正文。"""
    current = validate_filesystem_path(path)
    files, current_hashes = _inventory(current)
    payload = {
        "path": str(current),
        "file_count": len(files),
        "files": [p.name if current.is_file() else p.relative_to(current).as_posix() for p in files[:500]],
        "truncated": len(files) > 500,
        "compare_file_count": 0,
        "duplicate_file_count": 0,
        "duplicate_pairs": [],
    }
    if compare_with.strip():
        other = validate_filesystem_path(compare_with)
        other_files, other_hashes = _inventory(other)
        pairs = []
        for digest, paths in current_hashes.items():
            matches = other_hashes.get(digest, [])
            if matches:
                pairs.append({"path": paths[0], "matches": matches[:20]})
        payload.update({
            "compare_path": str(other),
            "compare_file_count": len(other_files),
            "duplicate_file_count": sum(len(item["matches"]) for item in pairs),
            "duplicate_pairs": pairs[:_MAX_DUPLICATE_PAIRS],
            "duplicate_pairs_truncated": len(pairs) > _MAX_DUPLICATE_PAIRS,
        })
    return json.dumps(payload, ensure_ascii=False)


@tool
def index_local_path(path: str) -> str:
    """将授权目录中的文件导入知识库；这是写操作，需要用户审批后才执行。"""
    source = validate_filesystem_path(path)
    if not _supported_files(source):
        return "未找到支持的文档类型，没有执行入库。"
    from config import EXTERNAL_DIR
    from src.ingestion.pipeline import run_add_path

    messages = []
    chunks = run_add_path(str(source), external_dir=str(EXTERNAL_DIR), echo_fn=messages.append)
    if chunks:
        from src.resources import ResourceManager
        ResourceManager.get_instance().invalidate_retriever_cache()
        return f"入库完成：新增 {chunks} 个片段。\n" + "\n".join(messages[-8:])
    return "没有新增片段（文件可能已存在、无可处理内容或入库未产生结果）。\n" + "\n".join(messages[-8:])
