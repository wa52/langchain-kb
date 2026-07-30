import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from src.api.schemas import ErrorResponse
from src.resources import app_lifespan

logger = logging.getLogger(__name__)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


def create_app() -> FastAPI:
    app = FastAPI(
        title="LangChain RAG Knowledge Base API",
        version="1.0.0",
        lifespan=app_lifespan,
    )

    from src.api.routers.health import router as health_router
    from src.api.routers.search import router as search_router
    from src.api.routers.chat import router as chat_router
    from src.api.routers.indexing import router as indexing_router

    app.include_router(health_router, prefix="/api/v1")
    app.include_router(search_router, prefix="/api/v1")
    app.include_router(chat_router, prefix="/api/v1")
    app.include_router(indexing_router, prefix="/api/v1")

    from fastapi_mcp import FastApiMCP
    app.state.mcp = FastApiMCP(
        app,
        include_operations=["search_knowledge", "answer_with_knowledge", "get_index_status"],
        name="LangChain RAG Knowledge Base",
        description="Semantic search, RAG Q&A, and index status for the knowledge base",
    )
    app.state.mcp.mount_http()

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
                detail=str(exc),
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

    return app


app = create_app()
