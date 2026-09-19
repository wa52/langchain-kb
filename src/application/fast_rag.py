"""One-call RAG for ordinary knowledge-base questions.

This module deliberately knows nothing about Deep Agents, LangGraph, MCP, or
tool selection.  It turns a bounded retrieval result into a single model call
and exposes timing data for the developer pane.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from collections.abc import Callable, Iterable
import re
import time
from typing import Any


_TERM_RE = re.compile(r"[A-Za-z0-9_]{2,}|[\u4e00-\u9fff]")
_COMMON_CHARS = frozenset("的是了在和与及对用有这那一个什么怎么如何可以请帮我把的")


@dataclass
class FastRagPlan:
    query: str
    documents: list[Any] = field(default_factory=list)
    context: str = ""
    relevant: bool = False
    sources: list[str] = field(default_factory=list)
    raw_docs_count: int = 0
    selected_docs_count: int = 0
    context_tokens: int = 0
    timings: dict[str, float] = field(default_factory=dict)
    llm_calls: int = 0

    def snapshot(self) -> dict[str, Any]:
        total = round(sum(self.timings.values()), 2)
        return {
            "route": "fast_rag",
            "total_ms": total,
            "stages": dict(self.timings),
            "llm_calls": self.llm_calls,
            "raw_docs_count": self.raw_docs_count,
            "selected_docs_count": self.selected_docs_count,
            "context_tokens": self.context_tokens,
            "relevant": self.relevant,
        }


class FastRagService:
    """Retrieve, gate, trim context, then make exactly one answer LLM call."""

    def __init__(
        self,
        *,
        retrieve: Callable[[str, int], list[Any]],
        llm_factory: Callable[[], Any],
        token_estimator: Callable[[str], int],
        top_k: int,
        fetch_k: int,
        max_context_tokens: int,
        gate_threshold: float,
    ) -> None:
        self._retrieve = retrieve
        self._llm_factory = llm_factory
        self._token_estimator = token_estimator
        self._top_k = max(1, top_k)
        self._fetch_k = max(self._top_k, fetch_k)
        self._max_context_tokens = max(1, max_context_tokens)
        self._gate_threshold = max(0.0, min(1.0, gate_threshold))

    def prepare(self, messages: list[dict], *, prefetched_documents: list[Any] | tuple[Any, ...] | None = None) -> FastRagPlan:
        query = str(messages[-1].get("content", "")).strip() if messages else ""
        plan = FastRagPlan(query=query)
        started = time.perf_counter()
        docs = list(prefetched_documents) if prefetched_documents is not None else list(self._retrieve(query, self._fetch_k) or [])
        plan.timings["search_ms"] = self._elapsed(started)
        plan.raw_docs_count = len(docs)

        started = time.perf_counter()
        plan.relevant = self.gate(query, docs)
        plan.timings["gate_ms"] = self._elapsed(started)
        if not plan.relevant:
            return plan

        started = time.perf_counter()
        plan.documents, plan.context, plan.sources, plan.context_tokens = self.build_context(docs)
        plan.selected_docs_count = len(plan.documents)
        plan.timings["context_ms"] = self._elapsed(started)
        # An empty bounded context is a miss even if the broad gate passed.
        plan.relevant = bool(plan.context)
        return plan

    def gate(self, query: str, documents: list[Any]) -> bool:
        """Cheap lexical relevance gate; never calls an LLM."""
        if not documents:
            return False
        terms = {term.lower() for term in _TERM_RE.findall(query) if term not in _COMMON_CHARS}
        if not terms:
            return False
        corpus = "\n".join(str(getattr(doc, "page_content", "")) for doc in documents).lower()
        matched = sum(1 for term in terms if term in corpus)
        return (matched / len(terms)) >= self._gate_threshold

    def build_context(self, documents: list[Any]) -> tuple[list[Any], str, list[str], int]:
        """Deduplicate and enforce a hard context budget without LLM compression."""
        selected: list[Any] = []
        sources: list[str] = []
        segments: list[str] = []
        used = 0
        seen: set[tuple[str, str]] = set()
        for doc in documents:
            if len(selected) >= self._top_k:
                break
            metadata = getattr(doc, "metadata", {}) or {}
            source = str(metadata.get("source", "unknown"))
            text = str(getattr(doc, "page_content", "")).strip()
            key = (source, " ".join(text[:180].split()))
            if not text or key in seen:
                continue
            seen.add(key)
            remaining = self._max_context_tokens - used
            if remaining <= 0:
                break
            max_chars = max(1, remaining * 4)
            excerpt = text[:max_chars]
            tokens = self._token_estimator(excerpt)
            if tokens > remaining:
                # The project estimator counts each CJK character, so this
                # is a safe upper bound for both CJK and Latin text.
                excerpt = excerpt[:remaining]
                tokens = self._token_estimator(excerpt)
            if not excerpt:
                continue
            selected.append(doc)
            if source not in sources:
                sources.append(source)
            segments.append(f"[来源: {source}]\n{excerpt}")
            used += tokens
        return selected, "\n\n---\n\n".join(segments), sources, used

    def prompt_messages(self, messages: list[dict], plan: FastRagPlan) -> list[dict]:
        history = [
            {"role": item.get("role", ""), "content": item.get("content", "")}
            for item in messages[:-1]
        ]
        system = (
            "你是个人知识库助手。仅根据给出的资料回答；资料不足时明确说明知识库没有足够依据。"
            "回答使用中文、简洁准确，不要提及内部检索实现。每个关键结论尽量保留 [来源: 文件名] 标记。\n\n"
            f"资料：\n{plan.context}"
        )
        return [
            {"role": "system", "content": system},
            *history,
            {"role": "user", "content": plan.query},
        ]

    def stream_answer(self, messages: list[dict], plan: FastRagPlan) -> Iterable[str]:
        started = time.perf_counter()
        plan.llm_calls += 1
        try:
            for chunk in self._llm_factory().stream(self.prompt_messages(messages, plan)):
                content = getattr(chunk, "content", chunk)
                if content:
                    yield str(content)
        finally:
            plan.timings["llm_ms"] = self._elapsed(started)

    @staticmethod
    def prepare_snapshot(plan: FastRagPlan, started: float) -> dict[str, Any]:
        snapshot = plan.snapshot()
        snapshot["total_ms"] = round((time.time() - started) * 1000, 2)
        return snapshot

    @staticmethod
    def citation_suffix(answer: str, sources: list[str]) -> str:
        missing = [source for source in sources if f"[来源: {source}]" not in answer]
        if not missing:
            return ""
        return "\n\n参考资料：\n" + "\n".join(f"- [来源: {source}]" for source in missing)

    @staticmethod
    def _elapsed(started: float) -> float:
        return round((time.perf_counter() - started) * 1000, 2)
