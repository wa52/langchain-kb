"""Analyze conversational topic continuity independently of route policy."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import re


_FOLLOW_UP = re.compile(r"^(那|这个|那个|第二种|参数呢|为什么|怎么|如何|继续|具体)")


@dataclass(frozen=True)
class ContextAssessment:
    previous_query: str | None = None
    topic_similarity: float = 0.0

    @property
    def is_knowledge_follow_up(self) -> bool:
        return self.previous_query is not None


class ContextAnalyzer:
    def __init__(self, topic_similarity: Callable[[str, str], float] | None = None, *, threshold: float = 0.55) -> None:
        self._topic_similarity = topic_similarity
        self._threshold = max(0.0, min(1.0, threshold))

    def analyze(self, query: str, history: list[dict]) -> ContextAssessment:
        text = " ".join((query or "").strip().lower().split())
        if not history or not (len(text) <= 28 or _FOLLOW_UP.match(text)):
            return ContextAssessment()
        for index in range(len(history) - 1, max(-1, len(history) - 5), -1):
            message = history[index]
            if message.get("role") != "assistant" or message.get("route") != "fast_rag":
                continue
            for user in reversed(history[:index]):
                if user.get("role") != "user":
                    continue
                previous = str(user.get("content", ""))
                similarity = self._topic_similarity(text, previous) if self._topic_similarity is not None else 1.0
                return ContextAssessment(previous if similarity >= self._threshold else None, similarity)
        return ContextAssessment()
