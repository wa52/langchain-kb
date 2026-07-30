import asyncio
from pathlib import Path

from fastapi import APIRouter, HTTPException

from src.api.dependencies import RmDep
from src.api.schemas import IndexRequest, IndexTaskResponse, TaskStatusResponse
from src.api.services.indexing import get_task_manager, run_index_task

router = APIRouter()


def _validate_path(path_str: str):
    if ".." in path_str.split("/") or ".." in path_str.split("\\"):
        raise HTTPException(status_code=400, detail="Path must not contain '..'")
    p = Path(path_str)
    if not p.exists():
        raise HTTPException(status_code=400, detail=f"Path not found: {path_str}")


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
