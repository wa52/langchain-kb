import asyncio
import re
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile

from src.api.dependencies import RmDep
from src.api.schemas import (
    IndexRequest,
    IndexTaskResponse,
    TaskStatusResponse,
    UploadTasksResponse,
)
from src.api.services.indexing import get_task_manager, run_index_task

router = APIRouter()

MAX_UPLOAD_BYTES = 50 * 1024 * 1024
_UPLOAD_CHUNK = 1024 * 1024


def _validate_path(path_str: str):
    if ".." in path_str.split("/") or ".." in path_str.split("\\"):
        raise HTTPException(status_code=400, detail="Path must not contain '..'")
    p = Path(path_str)
    if not p.exists():
        raise HTTPException(status_code=400, detail=f"Path not found: {path_str}")


def _sanitize_filename(name: str) -> str:
    """Neutralize path traversal and Windows-hostile names."""
    safe = Path(name or "").name
    safe = safe.strip().rstrip(". ")
    if not safe:
        return "upload.bin"
    if re.match(r"^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])$", safe, re.IGNORECASE):
        safe = "_" + safe
    if len(safe) > 200:
        safe = safe[:200]
    return safe


def _read_upload(file: UploadFile) -> bytes:
    """Read an upload in bounded chunks, rejecting oversized bodies early.

    Guards against unbounded buffering of a huge (possibly malicious) body.
    """
    data = bytearray()
    while True:
        chunk = file.file.read(_UPLOAD_CHUNK)
        if not chunk:
            break
        data.extend(chunk)
        if len(data) > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="File too large")
    return bytes(data)


def _reserve_unique(base: Path, name: str, data: bytes) -> Path:
    """Write ``data`` atomically under ``base`` with dedup naming (x, x_1, ...)."""
    stem, suffix = Path(name).stem, Path(name).suffix
    target = base / name
    counter = 1
    while True:
        try:
            with open(target, "xb") as fh:
                fh.write(data)
            return target
        except FileExistsError:
            target = base / f"{stem}_{counter}{suffix}"
            counter += 1


@router.post(
    "/documents/index",
    response_model=IndexTaskResponse,
    status_code=202,
    operation_id="start_index_task",
    summary="启动文档索引任务",
    description="将文件或目录添加到知识库并启动异步索引。立即返回 task_id，不等待索引完成。同一路径不可同时进行两个索引任务。",
)
async def index_documents(req: IndexRequest, rm: RmDep):
    _validate_path(req.path)
    mgr = get_task_manager()
    if mgr.has_active_task(req.path):
        raise HTTPException(status_code=409, detail=f"Already indexing: {req.path}")
    task_id = mgr.create_task(req.path)
    asyncio.create_task(run_index_task(task_id, req.path))
    return IndexTaskResponse(task_id=task_id, status="pending")


@router.get(
    "/index/tasks/{task_id}",
    response_model=TaskStatusResponse,
    operation_id="get_index_status",
    summary="查询索引任务状态",
    description="轮询异步索引任务的当前状态。任务状态机: pending → running → done / failed。",
)
def get_task(task_id: str):
    mgr = get_task_manager()
    task = mgr.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"Task not found: {task_id}")
    return TaskStatusResponse(
        task_id=task["task_id"],
        status=task["status"],
        progress=task.get("progress"),
        result=task.get("result"),
        error=task.get("error"),
    )


@router.post(
    "/documents/upload",
    response_model=UploadTasksResponse,
    status_code=202,
    operation_id="upload_documents",
    summary="上传并索引文档",
    description=(
        "接收一个或多个上传文件，保存到服务器数据目录（重名自动改名）后启动异步索引。"
        "每个文件对应一个索引任务，立即返回 task_id 列表，不等待索引完成。"
    ),
)
async def upload_documents(rm: RmDep, files: list[UploadFile] = File(...)):
    # ``rm`` is unused inside the handler; it only gates on resource readiness
    # (503 before the backend has finished startup).
    from config import EXTERNAL_DIR
    base = Path(EXTERNAL_DIR)
    base.mkdir(parents=True, exist_ok=True)

    # Validate + read the whole batch before writing anything, so an
    # oversized file cannot leave earlier files half-applied.
    staged: list[tuple[str, bytes]] = []
    for f in files:
        name = _sanitize_filename(f.filename or "upload.bin")
        staged.append((name, _read_upload(f)))

    mgr = get_task_manager()
    tasks: list[IndexTaskResponse] = []
    saved: list[str] = []
    for name, data in staged:
        target = _reserve_unique(base, name, data)
        if mgr.has_active_task(str(target)):
            raise HTTPException(status_code=409, detail=f"Already indexing: {target.name}")
        saved.append(target.name)
        task_id = mgr.create_task(str(target))
        asyncio.create_task(run_index_task(task_id, str(target), in_place=True))
        tasks.append(IndexTaskResponse(task_id=task_id, status="pending"))

    return UploadTasksResponse(tasks=tasks, saved=saved)
