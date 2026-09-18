"""Low-latency routing between direct LLM answers and the RAG agent.

The router is deliberately deterministic: asking another LLM to decide whether
to call the first LLM adds latency and can be less stable than a small policy.
Ambiguous domain questions route to RAG; ordinary conversation stays direct.
"""

from enum import StrEnum
import re


class QueryRoute(StrEnum):
    DIRECT = "direct"
    AGENT = "agent"


_DIRECT_PATTERNS = (
    r"^(你好|您好|嗨|hello|hi|早上好|下午好|晚上好)[！!。,.，\s]*$",
    r"^(谢谢|感谢|好的|好|明白了|知道了|再见|拜拜)[！!。,.，\s]*$",
    r"^(你是谁|你叫什么|介绍一下你自己)[？?。\s]*$",
)

_AGENT_TERMS = {
    "知识库", "资料", "文档", "来源", "引用", "检索", "rag",
    "工业视觉", "机器视觉", "缺陷", "检测", "分割", "识别", "定位",
    "测量", "相机", "镜头", "光源", "标定", "视觉项目", "算法选型",
    "项目方案", "项目验证", "spi", "aoi", "ocr", "yolo", "opencv",
    "联网", "搜索", "查一下", "最新", "官网", "网页",
}

_DIRECT_TASK_TERMS = {
    "翻译", "润色", "改写", "续写", "总结这段", "解释这句话",
    "写一段", "写个标题", "计算", "换一种说法",
}

_FOLLOW_UP_PATTERN = re.compile(r"^(那|那么|然后|为什么|怎么|如何|继续|具体呢|还有呢|举例|详细说说)")


def route_query(query: str, history: list[dict] | None = None) -> QueryRoute:
    """Choose the cheapest correct execution path for a user query."""
    text = " ".join((query or "").strip().lower().split())
    if not text:
        return QueryRoute.DIRECT
    if any(re.fullmatch(pattern, text, flags=re.IGNORECASE) for pattern in _DIRECT_PATTERNS):
        return QueryRoute.DIRECT
    if any(term in text for term in _DIRECT_TASK_TERMS) and not any(term in text for term in _AGENT_TERMS):
        return QueryRoute.DIRECT
    if any(term in text for term in _AGENT_TERMS):
        return QueryRoute.AGENT

    # A short follow-up after a grounded/tool-assisted answer should keep the
    # same execution path even if it omits the original domain nouns.
    if history and (len(text) <= 24 or _FOLLOW_UP_PATTERN.match(text)):
        for message in reversed(history[-4:]):
            if message.get("role") != "assistant":
                continue
            if message.get("route") == QueryRoute.AGENT or message.get("tools"):
                return QueryRoute.AGENT
            if "[来源:" in str(message.get("content", "")):
                return QueryRoute.AGENT
            break
    return QueryRoute.DIRECT


DIRECT_SYSTEM_PROMPT = """你是一个工业视觉 AI 工程助手。当前请求不需要检索知识库，也不要声称已经检索资料。
直接、准确地回答用户；简单问题保持简洁。若用户明确要求知识库资料、来源、工业视觉项目分析或最新外部信息，提醒其补充明确需求即可。
不要输出隐藏思维过程，不要虚构来源或工具执行结果。使用中文回答。"""
