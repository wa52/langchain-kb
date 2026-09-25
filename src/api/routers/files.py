import asyncio

from fastapi import APIRouter, HTTPException, Query, Response
from fastapi.responses import JSONResponse

from src.api.schemas import (
    IndexTaskResponse,
    SourceHealthAuditResponse,
    SourceHealthAuditStatus,
)
from src.application.files import list_files_view
from src.application.indexing import get_task_manager, run_remove_task
from src.api.services.source_health import (
    get_source_health_task_manager,
    run_source_health_task,
)

router = APIRouter()


@router.get(
    "/files",
    operation_id="list_files",
    summary="列出知识库已跟踪文件",
    description="返回 file_tracker 中记录的已入库文件（来源类型 + 相对路径 + 指纹）。",
)
def list_files():
    return JSONResponse(
        content=list_files_view(),
        headers={"Cache-Control": "no-store"},
    )


@router.post(
    "/files/health-audit",
    response_model=SourceHealthAuditResponse,
    status_code=202,
    operation_id="start_source_health_audit",
    summary="显式检查已索引知识源健康度",
    description=(
        "异步核对 tracker 中已索引文件的缺失、变更、重复和可访问状态。"
        "只检查已跟踪文件；逐文件读取并计算 SHA-256，不返回文档正文。"
        "该检查仅在显式调用时开始，不会因打开知识库页面而自动扫描。"
    ),
)
async def start_source_health_audit():
    manager = get_source_health_task_manager()
    try:
        task_id = manager.create_task()
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    asyncio.create_task(run_source_health_task(task_id))
    task = manager.get_task(task_id)
    return SourceHealthAuditResponse(
        task_id=task_id,
        status=task["status"],
        progress=task["progress"],
    )


@router.get(
    "/files/health-audit/{task_id}",
    response_model=SourceHealthAuditStatus,
    operation_id="get_source_health_audit",
    summary="查询知识源健康度检查任务",
    description="查询显式启动的源文件健康检查状态与问题摘要；只返回来源类型和相对文件名。",
)
def get_source_health_audit(task_id: str, response: Response):
    response.headers["Cache-Control"] = "no-store"
    task = get_source_health_task_manager().get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Source health audit task not found")
    return SourceHealthAuditStatus(
        task_id=task["task_id"],
        status=task["status"],
        progress=task["progress"],
        result=task.get("result"),
        error=task.get("error"),
        completed_at=task.get("completed_at"),
    )


@router.delete(
    "/files/{name}",
    response_model=IndexTaskResponse,
    status_code=202,
    operation_id="remove_file",
    summary="从知识库移除文件",
    description=(
        "从向量库删除该文件的全部 chunk，可选删除 data/external 下的副本，"
        "并重建 BM25 索引。异步执行，立即返回 task_id。"
    ),
)
async def remove_file(
    name: str,
    keep_file: bool = Query(False, description="仅从向量库删除，保留磁盘文件"),
):
    mgr = get_task_manager()
    key = f"remove:{name}"
    if mgr.has_active_task(key):
        raise HTTPException(status_code=409, detail=f"正在移除: {name}")
    task_id = mgr.create_task(key)
    asyncio.create_task(run_remove_task(task_id, name, keep_file=keep_file))
    return IndexTaskResponse(task_id=task_id, status="pending")
