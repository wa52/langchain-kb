from fastapi import APIRouter, Query

from src.retrieval.telemetry import retrieval_record_store

router = APIRouter()


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
