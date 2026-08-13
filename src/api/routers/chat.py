import asyncio
import json
import queue
import threading

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from src.api.schemas import ChatRequest, ChatResponse, ChatStreamRequest, CitationItem
from src.api.services.chat import chat_with_rag, extract_sources, stream_chat_events

router = APIRouter()

_END = object()


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
    description="发送用户消息给 RAG Agent，Agent 使用检索增强生成返回答案。支持会话历史延续。",
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
        "sources / message_end / error。客户端可通过中断请求停止生成，"
        "已产生的半截回答会保存到会话历史并标记 interrupted=true。"
    ),
)
async def chat_stream(req: ChatStreamRequest, request: Request):
    stop = threading.Event()
    q: "queue.Queue[object]" = queue.Queue(maxsize=256)

    def _put_control(item):
        """Terminal/control events must not be silently dropped.

        ``token`` events may be dropped under client backpressure, but an
        ``error`` / ``message_end`` / ``_END`` sentinel must still reach the
        consumer or the stream would hang waiting forever.
        """
        try:
            q.put_nowait(item)
        except queue.Full:
            try:
                q.put(item, timeout=2)
            except queue.Full:
                pass

    def producer():
        try:
            for event in stream_chat_events(req.query, req.session_id, stop):
                if event["type"] == "token":
                    try:
                        q.put_nowait(event)
                    except queue.Full:
                        pass
                else:
                    _put_control(event)
        except Exception as exc:
            _put_control({"type": "error", "data": {"error": str(exc)}})
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
