import asyncio

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

from src.api.schemas import IndexTaskResponse
from src.api.services.files import list_files_view
from src.api.services.indexing import get_task_manager, run_remove_task

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
