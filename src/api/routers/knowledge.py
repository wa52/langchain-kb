from fastapi import APIRouter

from src.api.dependencies import RmDep
from src.api.schemas import KnowledgeStatsResponse
from src.api.services.knowledge import get_knowledge_stats

router = APIRouter()


@router.get(
    "/knowledge/stats",
    response_model=KnowledgeStatsResponse,
    operation_id="knowledge_stats",
    summary="知识库概览统计",
    description="返回知识库轻量统计：文档数、chunks、BM25 同步状态、图谱实体/关系，以及最近一次索引任务的状态。读取缓存统计，不触发模型重新初始化。",
)
def knowledge_stats(rm: RmDep):
    return get_knowledge_stats(rm)
