from fastapi import APIRouter
from fastapi.responses import JSONResponse

from src.api.schemas import SettingsResponse
from src.api.services.settings import get_settings_view

router = APIRouter()


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
