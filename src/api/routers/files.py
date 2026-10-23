import asyncio

from fastapi import APIRouter, HTTPException, Query, Response
from fastapi.responses import JSONResponse

from src.api.dependencies import RmDep
from src.api.schemas import (
    IndexTaskResponse,
    TrackedFileRequest,
    SourceHealthAuditResponse,
    SourceHealthAuditStatus,
)
from src.application.files import list_files_view
from src.application.indexing import get_task_manager, run_remove_task, run_tracked_reindex_task, run_tracked_remove_task
from src.api.services.source_health import (
    get_source_health_task_manager,
    run_source_health_task,
)

router = APIRouter()


def _tracked_task_key(source_type: str, file_key: str) -> str:
    return "tracked:" + source_type + ":" + file_key.replace("\\", "/")


@router.post(
    "/files/reindex",
    response_model=IndexTaskResponse,
    status_code=202,
    operation_id="reindex_tracked_file",
    summary="重新索引已跟踪文件",
    description="按来源类型和相对路径原位替换已跟踪文件的索引，不复制或扫描其他文件。",
)
async def reindex_tracked_file(req: TrackedFileRequest, rm: RmDep):
    from src.api.services.files import resolve_tracked_file

    try:
        resolve_tracked_file(req.source_type, req.file_key)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (LookupError, FileNotFoundError) as exc:
        raise HTTPException(status_code=404, detail="已跟踪的来源文件不存在") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    key = _tracked_task_key(req.source_type, req.file_key)
    mgr = get_task_manager()
    try:
        task_id = mgr.create_task(key)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail="该文件正在重新索引") from exc
    asyncio.create_task(run_tracked_reindex_task(task_id, req.source_type, req.file_key))
    return IndexTaskResponse(task_id=task_id, status="pending")


@router.post(
    "/files/remove",
    response_model=IndexTaskResponse,
    status_code=202,
    operation_id="remove_tracked_file",
    summary="精确移除已跟踪文件的索引",
    description="按来源类型和相对路径移除索引及跟踪记录；原始磁盘文件保留。",
)
async def remove_tracked_file(req: TrackedFileRequest):
    from src.api.services.files import resolve_tracked_source

    try:
        resolve_tracked_source(req.source_type, req.file_key)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="已跟踪的来源记录不存在") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    key = _tracked_task_key(req.source_type, req.file_key)
    mgr = get_task_manager()
    try:
        task_id = mgr.create_task(key)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail="该文件正在执行索引操作") from exc
    asyncio.create_task(run_tracked_remove_task(task_id, req.source_type, req.file_key))
    return IndexTaskResponse(task_id=task_id, status="pending")


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
        "兼容接口，仅处理唯一的外部根目录文件名；同名、嵌套、目录或符号链接会拒绝。"
        "优先使用 POST /files/remove 并提供来源类型及完整相对路径。"
        "成功时可选删除原始文件，并重建 BM25 索引。异步执行，立即返回 task_id。"
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
