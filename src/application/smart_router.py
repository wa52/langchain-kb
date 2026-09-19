"""Explainable, no-LLM route selection for Direct / Fast RAG / Agent."""

from __future__ import annotations

from collections.abc import Callable
import re
import time
from typing import Any

from src.domain.routing import Route, RoutingDecision


_MUTATING_ACTION = re.compile(
    r"^(?:创建|新建|删除|修改|发送|保存|发布|写入|执行|运行)"
    r"|^(?:把|将).{0,30}(?:删除|修改|发送|保存|发布|写入)"
    r"|(?:帮我|请|给我).{0,16}(?:创建|新建|删除|修改|发送|保存|发布|写入|执行|运行)",
    re.I,
)
_ACTION_CONCEPT_QUESTION = re.compile(
    r"(?:创建|新建|删除|修改|发送|保存|发布|写入|执行|运行).{0,18}(?:是什么|为什么|哪些|怎么|如何|通常|一般|区别|用途|意义|作用)",
    re.I,
)
_EXTERNAL_ACTION = re.compile(
    r"(?:帮我|请|去|给我).{0,36}(?:(?:查|搜索|看看|看一下|查看|检查).{0,24}(?:github|仓库|网页|官网|最新|commit|提交|issue)|(?:github|仓库|网页|官网).{0,24}(?:查|搜索|看看|看一下|查看|检查))"
    r"|(?:查|搜索|检查).{0,20}(?:github|仓库|网页|官网)"
    r"|(?:帮我|请).{0,12}(?:联网|调用工具|mcp)"
    r"|(?:用|调用|使用).{0,8}(?:mcp|工具)"
    r"|(?:读取|查看).{0,12}(?:仓库|文件)",
    re.I,
)
_DIRECT_ACTIONS = frozenset(("翻译", "润色", "改写", "写一封", "解释", "计算"))
_RAG_HINTS = frozenset(("知识库", "资料", "文档", "之前", "项目", "参数", "方案", "训练", "检测", "标定", "halcon", "aoi", "ocr"))
_FOLLOW_UP = re.compile(r"^(那|这个|那个|第二种|参数呢|为什么|怎么|如何|继续|具体)")
_TERMS = re.compile(r"[A-Za-z0-9_]{2,}|[\u4e00-\u9fff]")
_NOISE = frozenset("的是了在和与及对用有这那一个什么怎么如何可以请帮我把的")


class SmartRouteService:
    """Use one retrieved candidate set for both routing and Fast RAG."""

    def __init__(
        self, retrieve: Callable[[str, int], list[Any]], *, fetch_k: int, rag_threshold: float,
        intent_classifier=None, topic_similarity: Callable[[str, str], float] | None = None,
        context_similarity_threshold: float = 0.55,
    ) -> None:
        self._retrieve = retrieve
        self._fetch_k = max(1, fetch_k)
        self._rag_threshold = max(0.0, min(1.0, rag_threshold))
        self._intent_classifier = intent_classifier
        self._topic_similarity = topic_similarity
        self._context_similarity_threshold = max(0.0, min(1.0, context_similarity_threshold))

    def decide(self, query: str, history: list[dict]) -> RoutingDecision:
        started = time.perf_counter()
        text = " ".join(query.strip().lower().split())
        intents = self._intent_classifier.classify(query) if self._intent_classifier is not None else {}
        # "保存文件时为什么…" and "执行链为什么…" discuss an action;
        # only an imperative request should enter the tool path.  Let conceptual
        # questions continue to retrieval, which preserves personal-history RAG.
        if not _ACTION_CONCEPT_QUESTION.search(text) and (_MUTATING_ACTION.search(text) or _EXTERNAL_ACTION.search(text)):
            return self._decision(Route.AGENT, 1.0, ("tool_or_side_effect_intent",), {"agent_intent": 1.0, "routing_ms": self._elapsed(started)})
        if intents.get("agent", 0.0) >= 0.82 and intents.get("agent", 0.0) > intents.get("direct", 0.0):
            return self._decision(Route.AGENT, intents["agent"], ("intent_prototype_agent",), {"agent_intent": intents["agent"], "routing_ms": self._elapsed(started)})
        if any(action in text for action in _DIRECT_ACTIONS) and not any(hint in text for hint in _RAG_HINTS):
            return self._decision(Route.DIRECT, 0.95, ("direct_task_intent",), {"direct_intent": 0.95, "routing_ms": self._elapsed(started)})

        context_route, context_query, context_similarity = self._context(history, text)
        retrieval_query = f"{context_query} {query}".strip() if context_query else query
        docs = tuple(self._retrieve(retrieval_query, self._fetch_k) or [])
        signals = self._signals(text, docs, context_route, context_similarity)
        signals.update({f"intent_{name}": value for name, value in intents.items()})
        signals["routing_ms"] = self._elapsed(started)
        confidence = round(
            0.58 * float(signals["semantic"])
            + 0.20 * float(signals["lexical"])
            + 0.12 * float(signals["rank"])
            + 0.10 * float(signals["context"]), 3,
        )
        confidence = round(min(1.0, confidence + 0.08 * float(intents.get("fast_rag", 0.0))), 3)
        reasons = []
        if signals["semantic"] >= self._rag_threshold:
            reasons.append("retrieval_semantic_hit")
        if signals["lexical"] >= 0.25:
            reasons.append("keyword_coverage")
        if signals["context"] >= 0.8:
            reasons.append("context_followup")
        if signals["hit_count"]:
            reasons.append("hybrid_candidates_available")
        route = Route.FAST_RAG if confidence >= self._rag_threshold else Route.DIRECT
        return self._decision(route, confidence, tuple(reasons or ["low_retrieval_confidence"]), signals, docs)

    def _context(self, history: list[dict], text: str) -> tuple[str | None, str | None, float]:
        if not history or not (len(text) <= 28 or _FOLLOW_UP.match(text)):
            return None, None, 0.0
        for index in range(len(history) - 1, max(-1, len(history) - 5), -1):
            message = history[index]
            if message.get("role") == "assistant" and message.get("route") == Route.FAST_RAG.value:
                for user in reversed(history[:index]):
                    if user.get("role") == "user":
                        previous_topic = str(user.get("content", ""))
                        if self._topic_similarity is not None:
                            similarity = self._topic_similarity(text, previous_topic)
                            if similarity < self._context_similarity_threshold:
                                return None, None, similarity
                            return Route.FAST_RAG.value, previous_topic, similarity
                        return Route.FAST_RAG.value, previous_topic, 1.0
        return None, None, 0.0

    @staticmethod
    def _signals(query: str, docs: tuple[Any, ...], context_route: str | None, context_similarity: float) -> dict[str, float | bool | int]:
        terms = {term.lower() for term in _TERMS.findall(query) if term not in _NOISE}
        corpus = "\n".join(str(getattr(doc, "page_content", "")) for doc in docs).lower()
        lexical = sum(term in corpus for term in terms) / max(1, len(terms))
        fusion = [float(getattr(doc, "fusion_score", 0.0)) for doc in docs]
        top1 = fusion[0] if fusion else 0.0
        top3_mean = sum(fusion[:3]) / min(3, len(fusion)) if fusion else 0.0
        gap = max(0.0, top1 - fusion[1]) if len(fusion) > 1 else top1
        agreement = any(getattr(doc, "dense_rank", None) and getattr(doc, "bm25_rank", None) for doc in docs)
        # Fused retrieval scores, not hit count, are the semantic backbone.
        semantic = min(1.0, 0.65 * top1 + 0.25 * top3_mean + 0.10 * gap)
        return {
            "semantic": round(semantic, 3), "lexical": round(lexical, 3),
            "rank": round(gap, 3), "top1_score": round(top1, 3),
            "top3_mean": round(top3_mean, 3), "top1_top2_gap": round(gap, 3),
            "context": 1.0 if context_route else 0.0,
            "context_topic_similarity": round(context_similarity, 3),
            "hit_count": len(docs), "dense_bm25_agreement": agreement,
        }

    @staticmethod
    def _decision(route, confidence, reasons, signals, documents=()):
        return RoutingDecision(route, confidence, tuple(reasons), dict(signals), tuple(documents))

    @staticmethod
    def _elapsed(started: float) -> float:
        return round((time.perf_counter() - started) * 1000, 2)
