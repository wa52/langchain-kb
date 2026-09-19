from fastapi import APIRouter

from src.api.dependencies import RmDep
from src.api.schemas import SearchRequest, SearchResponse, SearchResultItem
from src.application.search import search_documents
from src.bootstrap.composition import create_query_service

router = APIRouter()


@router.post(
    "/retrieval/search",
    response_model=SearchResponse,
    operation_id="search_knowledge",
    summary="搜索知识库",
    description="在向量库中执行语义搜索，返回相关文档片段。结果包含 chunk_id、content、source、score。",
)
def search(req: SearchRequest, rm: RmDep):
    results, elapsed_ms = search_documents(create_query_service(rm), req.query, req.top_k)
    return SearchResponse(
        results=[SearchResultItem(**r) for r in results],
        elapsed_ms=elapsed_ms,
    )
