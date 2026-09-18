from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from src.api.schemas import SettingsResponse
from src.application.settings import (
    get_settings_view,
    list_provider_models,
    set_graph_extraction_mode,
    set_llm_config,
    set_mcp_enabled,
    set_mcp_server_enabled,
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


class McpEnabledRequest(BaseModel):
    enabled: bool


class McpServerEnabledRequest(BaseModel):
    name: str
    enabled: bool


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
def settings(request: Request):
    view = get_settings_view()
    view["mcp_http_available"] = request.app.state.mcp is not None
    view["mcp_http_error"] = request.app.state.mcp_error
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


@router.post(
    "/settings/mcp",
    operation_id="set_mcp_enabled",
    summary="启用或停用外部 MCP 工具",
    description="保存全局 MCP 开关并丢弃当前 Agent；下一次 Agent 请求按新配置重建。",
)
def mcp_enabled(req: McpEnabledRequest):
    return JSONResponse(
        content=set_mcp_enabled(req.enabled),
        headers={"Cache-Control": "no-store"},
    )


@router.post(
    "/settings/mcp/server",
    operation_id="set_mcp_server_enabled",
    summary="启用或停用单个 MCP Server",
    description="原子更新 mcp.json 中已有 Server 的 enabled 字段，并热重载 Agent。",
)
def mcp_server_enabled(req: McpServerEnabledRequest):
    try:
        result = set_mcp_server_enabled(req.name, req.enabled)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse(content=result, headers={"Cache-Control": "no-store"})
