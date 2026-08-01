from fastapi import APIRouter, HTTPException

from src.api.schemas import (
    SessionListResponse,
    SessionDetailResponse,
    SessionSummary,
)
from src.agent.chat_history import list_sessions, load_history, delete_history

router = APIRouter()


@router.get(
    "/sessions",
    response_model=SessionListResponse,
    operation_id="list_sessions",
    summary="历史会话列表",
    description="列出所有已保存的对话会话，按时间倒序，包含标题、创建时间和轮数。",
)
def list_sessions_api():
    sessions = list_sessions()
    return SessionListResponse(
        sessions=[SessionSummary(**s) for s in sessions]
    )


@router.get(
    "/sessions/{session_id}",
    response_model=SessionDetailResponse,
    operation_id="get_session",
    summary="读取历史会话",
    description="返回指定会话 ID 的完整消息历史，用于在 Web 端恢复对话。",
)
def get_session(session_id: str):
    messages = load_history(session_id)
    if messages is None:
        raise HTTPException(status_code=404, detail=f"会话不存在: {session_id}")
    return SessionDetailResponse(id=session_id, messages=messages)


@router.delete(
    "/sessions/{session_id}",
    status_code=204,
    operation_id="delete_session",
    summary="删除历史会话",
    description="删除指定的历史会话文件。",
)
def delete_session_api(session_id: str):
    if not delete_history(session_id):
        raise HTTPException(status_code=404, detail=f"会话不存在: {session_id}")
