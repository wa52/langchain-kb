import time

from fastapi import APIRouter, Query

from src.api.schemas import RetrievalDebugResponse, RetrievalDebugResultItem, SearchRequest
from src.retrieval.telemetry import retrieval_record_store

router = APIRouter()


@router.post(
    "/retrieval/debug",
    response_model=RetrievalDebugResponse,
    operation_id="debug_retrieval",
    summary="调试知识检索",
    description="执行 Dense 与 BM25 检索并返回融合排序、各通道分数和总耗时。",
)
def debug_retrieval(request: SearchRequest) -> RetrievalDebugResponse:
    started = time.perf_counter()
    from src.application.knowledge import retrieve_scored_documents

    scored_documents = retrieve_scored_documents(request.query, request.top_k)
    results = []
    for item in scored_documents:
        metadata = item.metadata
        document = item.document
        results.append(RetrievalDebugResultItem(
            source=str(metadata.get("source") or "unknown"),
            chunk_id=str(getattr(document, "id", "") or metadata.get("chunk_id", "")),
            content=item.page_content,
            dense_score=round(float(item.dense_score), 4),
            bm25_score=round(float(item.bm25_score), 4),
            fusion_score=round(float(item.fusion_score), 4),
            dense_rank=item.dense_rank,
            bm25_rank=item.bm25_rank,
            rank=int(item.final_rank),
        ))
    return RetrievalDebugResponse(
        query=request.query,
        results=results,
        elapsed_ms=round((time.perf_counter() - started) * 1000, 2),
    )


@router.get(
    "/retrieval/records",
    operation_id="list_retrieval_records",
    summary="查询最近检索记录",
    description="查询最近的检索阶段耗时记录；记录仅保存在当前服务进程内。",
)
def list_retrieval_records(
    limit: int = Query(default=20, ge=1, le=256),
):
    return {"records": retrieval_record_store.recent(limit)}


@router.get(
    "/retrieval/records/{record_id}",
    operation_id="get_retrieval_record",
    summary="查询单条检索记录",
)
def get_retrieval_record(record_id: str):
    record = retrieval_record_store.get(record_id)
    if record is None:
        return {"record_id": record_id, "status": "not_found"}
    return {"status": "completed", "record": record}
