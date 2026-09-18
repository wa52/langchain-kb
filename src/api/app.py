import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from config import PRODUCT_NAME, PRODUCT_NAME_EN, PROJECT_ROOT
from src.api.web import web_app_html
from src.api.schemas import ErrorResponse
from src.bootstrap.lifecycle import app_lifespan

logger = logging.getLogger(__name__)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

# Built web client (Vite + React + TypeScript). When present, it is served
# instead of the embedded single-file UI and SPA routes fall back to it.
WEB_DIST = PROJECT_ROOT / "web" / "dist"


def _web_dist_available() -> bool:
    return (WEB_DIST / "index.html").exists()


def _spa_index() -> FileResponse:
    return FileResponse(WEB_DIST / "index.html")


def _mount_http_mcp(app: FastAPI) -> None:
    """Mount FastAPI-MCP without allowing an optional adapter to kill Web startup."""
    app.state.mcp = None
    app.state.mcp_error = None
    try:
        from fastapi_mcp import FastApiMCP
        mounted = FastApiMCP(
            app,
            include_operations=[
                "search_knowledge",
                "answer_with_knowledge",
                "get_index_status",
                "system_status",
            ],
            name=PRODUCT_NAME,
            description=f"Knowledge operations for the {PRODUCT_NAME_EN}",
        )
        mounted.mount_http()
        app.state.mcp = mounted
    except Exception as exc:
        app.state.mcp_error = str(exc)
        logger.error("HTTP MCP disabled because the adapter failed to initialize: %s", exc)


def create_app() -> FastAPI:
    from config import ensure_data_dirs
    ensure_data_dirs()

    app = FastAPI(
        title=f"{PRODUCT_NAME} API",
        version="1.0.0",
        lifespan=app_lifespan,
    )

    from src.api.routers.health import router as health_router
    from src.api.routers.status import router as status_router
    from src.api.routers.search import router as search_router
    from src.api.routers.chat import router as chat_router
    from src.api.routers.indexing import router as indexing_router
    from src.api.routers.sessions import router as sessions_router
    from src.api.routers.knowledge import router as knowledge_router
    from src.api.routers.diagnostics import router as diagnostics_router
    from src.api.routers.settings import router as settings_router
    from src.api.routers.sync import router as sync_router
    from src.api.routers.files import router as files_router

    app.include_router(health_router, prefix="/api/v1")
    app.include_router(status_router, prefix="/api/v1")
    app.include_router(search_router, prefix="/api/v1")
    app.include_router(chat_router, prefix="/api/v1")
    app.include_router(indexing_router, prefix="/api/v1")
    app.include_router(sessions_router, prefix="/api/v1")
    app.include_router(knowledge_router, prefix="/api/v1")
    app.include_router(diagnostics_router, prefix="/api/v1")
    app.include_router(settings_router, prefix="/api/v1")
    app.include_router(sync_router, prefix="/api/v1")
    app.include_router(files_router, prefix="/api/v1")

    @app.get("/", include_in_schema=False, response_class=HTMLResponse)
    async def landing_page():
        if _web_dist_available():
            return _spa_index()
        return web_app_html()

    if _web_dist_available() and (WEB_DIST / "assets").is_dir():
        app.mount(
            "/assets",
            StaticFiles(directory=WEB_DIST / "assets"),
            name="web-assets",
        )

    _mount_http_mcp(app)

    if _web_dist_available():

        @app.get("/{full_path:path}", include_in_schema=False)
        async def spa_fallback(full_path: str):
            # API/MCP/docs paths that did not match an actual route stay JSON 404;
            # everything else is the single-page app's client-side route.
            first = full_path.lower().split("/", 1)[0]
            if first in ("api", "mcp", "docs", "redoc", "openapi.json", "assets"):
                raise HTTPException(status_code=404, detail=f"Route GET /{full_path} not found")
            return _spa_index()

    @app.exception_handler(HTTPException)
    async def http_exception_handler(_request: Request, exc: HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content=ErrorResponse(
                error=exc.detail or "HTTP error",
                detail=exc.detail,
            ).model_dump(),
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(_request: Request, exc: Exception):
        logger.exception("Unhandled exception")
        return JSONResponse(
            status_code=500,
            content=ErrorResponse(
                error="Internal server error",
                detail=None,
            ).model_dump(),
        )

    @app.middleware("http")
    async def catch_unmatched_routes(request: Request, call_next):
        response = await call_next(request)
        if response.status_code == 404:
            from starlette.responses import JSONResponse as _JSONResponse
            return _JSONResponse(
                status_code=404,
                content=ErrorResponse(
                    error="Not Found",
                    detail=f"Route {request.method} {request.url.path} not found",
                ).model_dump(),
            )
        return response

    from src.api.security import lan_access_middleware
    app.middleware("http")(lan_access_middleware)

    return app


app = create_app()
