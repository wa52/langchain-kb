import re

from fastapi import APIRouter

from src.api.schemas import ChatRequest, ChatResponse, CitationItem
from src.api.services.chat import chat_with_rag

router = APIRouter()

_CITATION_PATTERN = re.compile(r"\[来源:\s*([^\]]+)\]")


def _extract_citations(answer: str) -> list[dict]:
    seen = set()
    citations = []
    for match in _CITATION_PATTERN.finditer(answer):
        source = match.group(1).strip()
        if source and source not in seen:
            seen.add(source)
            citations.append({"source": source, "chunk_id": "", "excerpt": None})
    return citations


@router.post(
    "/chat",
    response_model=ChatResponse,
    operation_id="answer_with_knowledge",
    summary="与 RAG 助手对话",
    description="发送用户消息给 RAG Agent，Agent 使用检索增强生成返回答案。支持会话历史延续。",
)
def chat(req: ChatRequest):
    answer, session_id, elapsed_ms = chat_with_rag(req.query, req.session_id)
    citations = _extract_citations(answer)
    return ChatResponse(
        answer=answer,
        citations=[CitationItem(**c) for c in citations],
        conversation_id=session_id,
        elapsed_ms=elapsed_ms,
    )
