from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from src.api.services import sync

router = APIRouter()


class SyncDirRequest(BaseModel):
    path: str


@router.get(
    "/sync/status",
    operation_id="get_sync_status",
    summary="定时同步状态",
    description="返回经验库定时同步的配置与最近一次运行结果（目录、间隔、上次同步时间、是否正在运行）。",
)
def sync_status():
    return JSONResponse(content=sync.get_sync_view(), headers={"Cache-Control": "no-store"})


@router.post(
    "/sync/dirs",
    operation_id="add_sync_dir",
    summary="添加定时同步目录",
    description="把一个服务器本机目录加入定时同步列表（持久化到 .env 的 EXPERIENCE_DIRS）。",
)
def add_sync_dir(req: SyncDirRequest):
    try:
        return JSONResponse(content=sync.add_sync_dir(req.path))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete(
    "/sync/dirs",
    operation_id="remove_sync_dir",
    summary="移除定时同步目录",
)
def remove_sync_dir(path: str = Query(..., description="要移除的目录路径")):
    return JSONResponse(content=sync.remove_sync_dir(path))


@router.post(
    "/sync/run",
    operation_id="run_sync",
    summary="立即同步经验库",
    description="后台执行一次经验库增量同步（正在运行时不重复启动）。",
)
async def run_sync():
    started = await sync.run_sync_now()
    return JSONResponse(
        content={"running": True, "started": started},
        status_code=202,
        headers={"Cache-Control": "no-store"},
    )
