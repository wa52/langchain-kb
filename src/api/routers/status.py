from fastapi import APIRouter

from src.api.dependencies import RmDep
from src.api.schemas import SystemStatusResponse
from src.api.services.status import get_system_status

router = APIRouter()


@router.get(
    "/status",
    response_model=SystemStatusResponse,
    operation_id="system_status",
    summary="系统状态监控",
    description="返回各关键组件（embedding / LLM / 向量库 / BM25 / 知识图谱 / Agent / 索引任务）的实时状态、耗时与错误信息，以及索引版本与数据规模概览。不触发模型重新初始化。",
)
def status(rm: RmDep):
    return get_system_status(rm)
