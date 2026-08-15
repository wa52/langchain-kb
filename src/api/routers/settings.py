from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from src.api.schemas import SettingsResponse
from src.api.services.settings import get_settings_view, set_graph_extraction_mode

router = APIRouter()


class GraphModeRequest(BaseModel):
    enabled: bool


@router.get(
    "/settings",
    response_model=SettingsResponse,
    operation_id="get_settings",
    summary="读取配置（只读，不包含密钥）",
    description=(
        "返回只读配置快照：路径、模型、功能开关与安全状态。"
        "不返回任何 API Key、Token 或密码明文。"
    ),
)
def settings():
    view = get_settings_view()
    return JSONResponse(
        content=view,
        headers={"Cache-Control": "no-store"},
    )


@router.post(
    "/settings/graph-mode",
    operation_id="set_graph_extraction_mode",
    summary="切换知识图谱抽取模式（jieba / LLM）",
    description=(
        "持久化 ENABLE_GRAPH_LLM_EXTRACTION 到 .env 并即时生效，"
        "影响下一次索引任务。jieba 模式本地零 API 调用（快）；"
        "LLM 模式使用 DeepSeek（慢但抽取质量更高）。"
    ),
)
def graph_mode(req: GraphModeRequest):
    result = set_graph_extraction_mode(req.enabled)
    return JSONResponse(
        content=result,
        headers={"Cache-Control": "no-store"},
    )
