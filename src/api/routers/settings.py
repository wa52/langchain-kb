from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from src.api.schemas import SettingsResponse
from src.application.settings import (
    get_settings_view,
    list_provider_models,
    set_graph_extraction_mode,
    set_llm_config,
)

router = APIRouter()


class GraphModeRequest(BaseModel):
    enabled: bool


class LlmConfigRequest(BaseModel):
    provider: str
    model: str
    base_url: str
    api_key: str | None = None


class LlmModelsRequest(BaseModel):
    provider: str
    base_url: str
    api_key: str | None = None


@router.get(
    "/settings",
    response_model=SettingsResponse,
    operation_id="get_settings",
    summary="读取配置（不包含密钥）",
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


@router.post(
    "/settings/llm",
    operation_id="set_llm_config",
    summary="切换 LLM API",
    description="保存并热切换到 OpenAI-compatible API；留空 api_key 表示沿用已保存密钥。",
)
def llm_config(req: LlmConfigRequest):
    try:
        result = set_llm_config(req.provider, req.model, req.base_url, req.api_key)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse(content=result, headers={"Cache-Control": "no-store"})


@router.post(
    "/settings/llm/models",
    operation_id="list_llm_models",
    summary="读取供应商模型列表",
    description="通过供应商的 OpenAI-compatible /models 接口读取真实模型名称，不保存 API Key。",
)
def llm_models(req: LlmModelsRequest):
    try:
        models = list_provider_models(req.provider, req.base_url, req.api_key)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse(content={"models": models}, headers={"Cache-Control": "no-store"})
