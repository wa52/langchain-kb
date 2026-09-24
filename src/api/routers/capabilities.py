from fastapi import APIRouter, Request

from src.api.schemas import CapabilityCatalogResponse
from src.application.capabilities import capability_catalog
from src.application.settings import get_settings_view

router = APIRouter()


@router.get(
    "/capabilities",
    response_model=CapabilityCatalogResponse,
    operation_id="list_capabilities",
    summary="列出可用工具与 MCP 状态",
    description="只读展示已注册工具元数据及 MCP 发现状态；不触发连接、工具执行或返回凭据。",
)
def list_capabilities(request: Request) -> CapabilityCatalogResponse:
    harness = getattr(request.app.state, "harness", None)
    settings = get_settings_view()
    return capability_catalog(
        getattr(harness, "tools", None),
        settings["mcp_servers"],
        mcp_enabled=settings["mcp_enabled"],
    )
