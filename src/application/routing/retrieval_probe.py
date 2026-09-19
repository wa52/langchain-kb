"""One scored retrieval probe shared by routing and Fast RAG."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import re
from typing import Any


_TERMS = re.compile(r"[A-Za-z0-9_]{2,}|[\u4e00-\u9fff]")
_NOISE = frozenset("的是了在和与及对用有这那一个什么怎么如何可以请帮我把的")


@dataclass(frozen=True)
class RetrievalProbe:
    documents: tuple[Any, ...]
    semantic: float
    lexical: float
    rank_gap: float
    top1_score: float
    top3_mean: float
    dense_bm25_agreement: bool

    def signals(self, *, context: bool, topic_similarity: float) -> dict[str, float | bool | int]:
        return {
            "semantic": self.semantic, "lexical": self.lexical, "rank": self.rank_gap,
            "top1_score": self.top1_score, "top3_mean": self.top3_mean,
            "top1_top2_gap": self.rank_gap, "context": 1.0 if context else 0.0,
            "context_topic_similarity": topic_similarity, "hit_count": len(self.documents),
            "dense_bm25_agreement": self.dense_bm25_agreement,
        }


class RetrievalProbeService:
    def __init__(self, retrieve: Callable[[str, int], list[Any]], *, fetch_k: int) -> None:
        self._retrieve = retrieve
        self._fetch_k = max(1, fetch_k)

    def probe(self, query: str) -> RetrievalProbe:
        docs = tuple(self._retrieve(query, self._fetch_k) or [])
        terms = {term.lower() for term in _TERMS.findall(query) if term not in _NOISE}
        corpus = "\n".join(str(getattr(doc, "page_content", "")) for doc in docs).lower()
        lexical = sum(term in corpus for term in terms) / max(1, len(terms))
        fusion = [float(getattr(doc, "fusion_score", 0.0)) for doc in docs]
        top1 = fusion[0] if fusion else 0.0
        top3_mean = sum(fusion[:3]) / min(3, len(fusion)) if fusion else 0.0
        gap = max(0.0, top1 - fusion[1]) if len(fusion) > 1 else top1
        agreement = any(getattr(doc, "dense_rank", None) and getattr(doc, "bm25_rank", None) for doc in docs)
        semantic = min(1.0, 0.65 * top1 + 0.25 * top3_mean + 0.10 * gap)
        return RetrievalProbe(docs, round(semantic, 3), round(lexical, 3), round(gap, 3), round(top1, 3), round(top3_mean, 3), agreement)
