import time
import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

from src.api.schemas import (
    RetrievalDebugResponse,
    RetrievalDebugResultItem,
    RetrievalEvaluationLatestResponse,
    ToolSelectionEvaluationReportResponse,
    ToolSelectionEvaluationLatestResponse,
    SearchRequest,
)
from src.retrieval.telemetry import retrieval_record_store

router = APIRouter()
RETRIEVAL_EVAL_REPORT_PATH = Path(__file__).resolve().parents[3] / "evals" / "retrieval" / "reports" / "latest.json"
TOOL_EVAL_REPORT_PATH = Path(__file__).resolve().parents[3] / "evals" / "tools" / "reports" / "latest.json"


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
    "/evaluations/retrieval/latest",
    response_model=RetrievalEvaluationLatestResponse,
    operation_id="get_retrieval_evaluation",
    summary="查询最近的隔离检索评测",
    description="读取基于仓库冻结示例语料生成的检索回归报告；不会读取当前用户知识库。",
)
def get_retrieval_evaluation() -> RetrievalEvaluationLatestResponse:
    if not RETRIEVAL_EVAL_REPORT_PATH.is_file():
        return RetrievalEvaluationLatestResponse(
            status="empty",
            message="尚无检索评测报告，请运行隔离基准后刷新。",
        )
    try:
        report = json.loads(RETRIEVAL_EVAL_REPORT_PATH.read_text(encoding="utf-8"))
        return RetrievalEvaluationLatestResponse(status="completed", report=report)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(status_code=500, detail="检索评测报告不可读") from exc


@router.get(
    "/evaluations/tools/latest",
    response_model=ToolSelectionEvaluationLatestResponse,
    operation_id="get_tool_selection_evaluation",
    summary="查询最近的离线工具选择评测",
    description="读取合成查询集上的规则与 Jev 适配器模拟评测；不会调用外部 Jev 服务。",
)
def get_tool_selection_evaluation() -> ToolSelectionEvaluationLatestResponse:
    if not TOOL_EVAL_REPORT_PATH.is_file():
        return ToolSelectionEvaluationLatestResponse(
            status="empty",
            message="尚无工具选择评测报告，请运行 python -m evals.tools.run 后刷新。",
        )
    try:
        report = json.loads(TOOL_EVAL_REPORT_PATH.read_text(encoding="utf-8"))
        if report.get("external_provider_called") is not False:
            raise ValueError("tool evaluation report must be offline")
        validated_report = ToolSelectionEvaluationReportResponse.model_validate(report)
        return ToolSelectionEvaluationLatestResponse(status="completed", report=validated_report)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(status_code=500, detail="工具选择评测报告不可读") from exc


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
