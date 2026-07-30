from fastapi import APIRouter

from src.api.dependencies import RmDep
from src.api.schemas import HealthResponse
from src.api.services.health import get_health_status

router = APIRouter()


@router.get(
    "/health",
    response_model=HealthResponse,
    operation_id="health_check",
    summary="健康检查",
    description="返回系统运行状态，包含启动时间、索引版本号、向量库文档数和知识图谱实体数。不触发模型重新初始化。",
)
def health(rm: RmDep):
    return get_health_status(rm)
