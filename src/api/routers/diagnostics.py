import asyncio

from fastapi import APIRouter, HTTPException

from src.api.dependencies import RmDep
from src.api.schemas import (
    DiagnosticsTaskResponse,
    DiagnosticsTaskStatus,
    RepairRequest,
    RepairResponse,
)
from src.api.services.diagnostics import (
    get_diagnostics_task_manager,
    repair_check,
    run_diagnostics_task,
)

router = APIRouter()


@router.post(
    "/diagnostics",
    response_model=DiagnosticsTaskResponse,
    status_code=202,
    operation_id="run_diagnostics",
    summary="运行完整诊断",
    description=(
        "显式触发完整诊断：逐组件探测（embedding / LLM / 向量库 / BM25 / 图谱 / "
        "Agent / 索引任务等），只读，可能耗时较长（会加载模型等）。"
        "立即返回 task_id，结果通过 GET /diagnostics/tasks/{id} 轮询。"
    ),
)
async def run_diagnostics(rm: RmDep):
    mgr = get_diagnostics_task_manager()
    if mgr.has_active():
        raise HTTPException(status_code=409, detail="Diagnostics already running")
    task_id = mgr.create_task()
    asyncio.create_task(run_diagnostics_task(task_id))
    return DiagnosticsTaskResponse(task_id=task_id, status="pending")


@router.get(
    "/diagnostics/tasks/{task_id}",
    response_model=DiagnosticsTaskStatus,
    operation_id="get_diagnostics_status",
    summary="查询完整诊断结果",
    description="轮询完整诊断任务状态；status 为 done 时携带逐项检查结果与汇总。",
)
def get_diagnostics(task_id: str):
    mgr = get_diagnostics_task_manager()
    task = mgr.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"Diagnostics task not found: {task_id}")
    return DiagnosticsTaskStatus(
        task_id=task["task_id"],
        status=task["status"],
        result=task.get("result"),
        error=task.get("error"),
    )


@router.post(
    "/diagnostics/repair",
    response_model=RepairResponse,
    operation_id="repair_diagnostics",
    summary="修复指定诊断项",
    description=(
        "对已完成诊断任务中的某个失败项执行修复（需用户显式确认）。"
        "仅修复可自动修复的项；不可修复项返回 repaired=false。"
    ),
)
async def repair(req: RepairRequest, rm: RmDep):
    mgr = get_diagnostics_task_manager()
    task = mgr.get_task(req.task_id)
    if task is None or task.get("status") != "done":
        raise HTTPException(status_code=400, detail="Diagnostics must be run first")
    name = req.name.strip()
    result = task.get("result") or {}
    failed_repairable = {
        c["name"] for c in result.get("checks", [])
        if not c.get("ok") and c.get("repairable")
    }
    if name not in failed_repairable:
        raise HTTPException(status_code=400, detail=f"Check not repairable: {name}")
    repaired = await repair_check(name)
    return RepairResponse(name=name, repaired=repaired)
