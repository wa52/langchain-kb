"""Thin coordinator for Intent, Context, Probe, and Policy modules."""

from __future__ import annotations

from collections.abc import Callable
import time
from typing import Any

from src.application.routing.context import ContextAnalyzer
from src.application.routing.intent import IntentClassifier
from src.application.routing.policy import RoutingPolicy
from src.application.routing.retrieval_probe import RetrievalProbeService
from src.domain.routing import Intent


class SmartRouteService:
    def __init__(self, retrieve: Callable[[str, int], list[Any]], *, fetch_k: int, rag_threshold: float, intent_classifier=None, topic_similarity=None, context_similarity_threshold: float = 0.55) -> None:
        self._intent = IntentClassifier(intent_classifier)
        self._context = ContextAnalyzer(topic_similarity, threshold=context_similarity_threshold)
        self._probe = RetrievalProbeService(retrieve, fetch_k=fetch_k)
        self._policy = RoutingPolicy(rag_threshold=rag_threshold)

    def decide(self, query: str, history: list[dict]):
        started = time.perf_counter()
        intent = self._intent.assess(query)
        context = self._context.analyze(query, history)
        # Keep a rejected short follow-up observable in the trace, while it
        # remains a direct route because ContextAnalyzer did not inherit it.
        needs_probe = intent.intent is Intent.KNOWLEDGE or context.is_knowledge_follow_up or context.topic_similarity > 0.0
        retrieval_query = f"{context.previous_query} {query}".strip() if context.previous_query else query
        probe = self._probe.probe(retrieval_query) if needs_probe else None
        return self._policy.decide(intent, context, probe, routing_ms=round((time.perf_counter() - started) * 1000, 2))
