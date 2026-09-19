import asyncio
import json
import queue
import threading

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from src.api.schemas import ChatRequest, ChatResponse, ChatStreamRequest, ChatResumeRequest, CitationItem
from src.application.chat import chat_with_rag, extract_sources, stream_chat_events, resume_chat_events
from src.harness import trace_store

router = APIRouter()


@router.get("/traces/{run_id}", operation_id="get_agent_trace", summary="查询已完成 Agent Trace")
def get_agent_trace(run_id: str):
    trace = trace_store.get(run_id)
    if trace is None:
        return {"run_id": run_id, "status": "not_found"}
    return {"status": "completed", "trace": trace}

_END = object()


@router.post(
    "/chat/resume",
    operation_id="resume_chat",
    summary="恢复等待审批的 Agent 运行",
    description="使用同一 session_id 恢复被危险工具审批中断的 Agent 运行。",
)
def chat_resume(req: ChatResumeRequest):
    stop = threading.Event()
    events = list(resume_chat_events(
        req.session_id, req.decision, req.message, stop, decisions=req.decisions
    ))
    return {"session_id": req.session_id, "events": events}


def _sse(event: dict) -> str:
    return (
        f"event: {event['type']}\n"
        f"data: {json.dumps(event['data'], ensure_ascii=False)}\n\n"
    )


@router.post(
    "/chat",
    response_model=ChatResponse,
    operation_id="answer_with_knowledge",
    summary="与 RAG 助手对话",
    description=(
        "发送用户消息给 RAG Agent，Agent 使用检索增强生成返回答案。支持会话历史延续。"
        "边界说明：本操作不修改知识库与配置；唯一持久化是写入对话会话历史（JSON）。"
    ),
)
def chat(req: ChatRequest):
    answer, session_id, elapsed_ms = chat_with_rag(req.query, req.session_id)
    return ChatResponse(
        answer=answer,
        citations=[CitationItem(**c) for c in extract_sources(answer)],
        conversation_id=session_id,
        elapsed_ms=elapsed_ms,
    )


@router.post(
    "/chat/stream",
    response_class=StreamingResponse,
    operation_id="chat_stream",
    summary="流式对话",
    description=(
        "POST + fetch readable stream，SSE 事件：message_start / token / "
        "tool / verification / approval_required / sources / message_end / error。客户端可通过中断请求停止生成，"
        "已产生的半截回答会保存到会话历史并标记 interrupted=true。"
    ),
)
async def chat_stream(req: ChatStreamRequest, request: Request):
    stop = threading.Event()
    # Backpressure pauses the producer rather than dropping answer text or
    # allowing an unbounded queue to consume memory for a slow client.
    q: "queue.Queue[object]" = queue.Queue(maxsize=256)

    def _put_control(item):
        """Terminal/control events must not be silently dropped.

        ``token`` events may be dropped under client backpressure, but an
        ``error`` / ``message_end`` / ``_END`` sentinel must still reach the
        consumer or the stream would hang waiting forever.
        """
        while not stop.is_set():
            try:
                q.put(item, timeout=0.1)
                return
            except queue.Full:
                continue

    def producer():
        try:
            for event in stream_chat_events(req.query, req.session_id, stop):
                if event["type"] == "token":
                    _put_control(event)
                else:
                    _put_control(event)
        except Exception as exc:
            message = str(exc)
            if "MCP error" in message or "Invalid arguments for tool" in message:
                message = "浏览器工具暂时不可用，请稍后重试。"
            _put_control({"type": "error", "data": {"error": message}})
        finally:
            _put_control(_END)

    loop = asyncio.get_running_loop()
    task = loop.run_in_executor(None, producer)

    async def event_source():
        try:
            while True:
                try:
                    item = q.get_nowait()
                except queue.Empty:
                    if await request.is_disconnected():
                        stop.set()
                        break
                    await asyncio.sleep(0.01)
                    continue
                if item is _END:
                    break
                if await request.is_disconnected():
                    stop.set()
                    break
                yield _sse(item)
        finally:
            stop.set()
            try:
                await asyncio.wait_for(asyncio.shield(task), timeout=15)
            except Exception:
                pass

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
