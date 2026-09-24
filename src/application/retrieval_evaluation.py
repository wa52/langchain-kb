"""Deterministic, dependency-injected retrieval ranking metrics."""

from __future__ import annotations

import math
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RetrievalCaseResult:
    case_id: str
    relevant_ids: tuple[str, ...]
    retrieved_relevant_ids: tuple[str, ...]
    first_relevant_rank: int | None
    hits_at_k: dict[int, int]
    reciprocal_rank: float
    elapsed_ms: float

    def snapshot(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "relevant_ids": list(self.relevant_ids),
            "retrieved_relevant_ids": list(self.retrieved_relevant_ids),
            "first_relevant_rank": self.first_relevant_rank,
            "hits_at_k": {str(k): value for k, value in self.hits_at_k.items()},
            "reciprocal_rank": round(self.reciprocal_rank, 4),
            "elapsed_ms": round(self.elapsed_ms, 2),
        }


@dataclass(frozen=True)
class RetrievalEvaluation:
    total: int
    recall_at_k: dict[int, float]
    mrr: float
    p50_ms: float
    p95_ms: float
    cases: tuple[RetrievalCaseResult, ...]

    def snapshot(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "recall_at_k": {str(k): value for k, value in self.recall_at_k.items()},
            "mrr": self.mrr,
            "latency_ms": {"p50": self.p50_ms, "p95": self.p95_ms},
            "cases": [case.snapshot() for case in self.cases],
        }


def _validated_cases(cases: Iterable[Mapping[str, Any]]) -> list[tuple[str, str, tuple[str, ...]]]:
    normalized: list[tuple[str, str, tuple[str, ...]]] = []
    seen: set[str] = set()
    for index, case in enumerate(cases):
        label = f"case at index {index}"
        if not isinstance(case, Mapping):
            raise ValueError(f"{label} must be an object")
        case_id = str(case.get("id", "")).strip()
        query = str(case.get("query", "")).strip()
        raw_relevant = case.get("relevant_ids")
        if not case_id:
            raise ValueError(f"{label} requires a non-empty id")
        if case_id in seen:
            raise ValueError(f"duplicate retrieval case id: {case_id}")
        if not query:
            raise ValueError(f"retrieval case {case_id} requires a non-empty query")
        if not isinstance(raw_relevant, list) or not raw_relevant:
            raise ValueError(f"retrieval case {case_id} requires relevant_ids")
        relevant = tuple(dict.fromkeys(str(item).strip() for item in raw_relevant))
        if any(not item for item in relevant):
            raise ValueError(f"retrieval case {case_id} has an empty relevant id")
        seen.add(case_id)
        normalized.append((case_id, query, relevant))
    if not normalized:
        raise ValueError("retrieval evaluation requires at least one case")
    return normalized


def _result_id(result: Any) -> str:
    if isinstance(result, Mapping):
        metadata = result.get("metadata", {})
        direct_id = result.get("chunk_id")
    else:
        metadata = getattr(result, "metadata", {}) or {}
        direct_id = getattr(result, "chunk_id", None)
    metadata = metadata if isinstance(metadata, Mapping) else {}
    return str(direct_id or metadata.get("chunk_id") or "").strip()


def _percentile(values: Sequence[float], percentile: float) -> float:
    ordered = sorted(values)
    index = max(0, math.ceil(percentile * len(ordered)) - 1)
    return round(ordered[index], 2)


def evaluate_retrieval(
    cases: Iterable[Mapping[str, Any]],
    retrieve: Callable[[str, int], Sequence[Any]],
    *,
    ks: Sequence[int] = (1, 3, 5),
) -> RetrievalEvaluation:
    """Score ordered retrieval outputs against independently labelled chunk IDs.

    The callback is the only system seam. Retrieval metrics are deterministic;
    elapsed timings are observations and therefore vary across executions.
    """
    normalized = _validated_cases(cases)
    cutoffs = tuple(dict.fromkeys(ks))
    if not cutoffs or any(not isinstance(k, int) or isinstance(k, bool) or k < 1 for k in cutoffs):
        raise ValueError("ks must contain positive integers")
    limit = max(cutoffs)
    results: list[RetrievalCaseResult] = []

    for case_id, query, relevant_ids in normalized:
        started = time.perf_counter()
        ranked = list(retrieve(query, limit) or ())
        elapsed_ms = (time.perf_counter() - started) * 1000
        ranked_ids = [_result_id(item) for item in ranked]
        first_rank = next(
            (rank for rank, item_id in enumerate(ranked_ids, 1) if item_id in relevant_ids),
            None,
        )
        retrieved_relevant = tuple(dict.fromkeys(
            item_id for item_id in ranked_ids if item_id in relevant_ids
        ))
        results.append(RetrievalCaseResult(
            case_id=case_id,
            relevant_ids=relevant_ids,
            retrieved_relevant_ids=retrieved_relevant,
            first_relevant_rank=first_rank,
            hits_at_k={k: len({item for item in ranked_ids[:k] if item in relevant_ids}) for k in cutoffs},
            reciprocal_rank=1 / first_rank if first_rank else 0.0,
            elapsed_ms=elapsed_ms,
        ))

    recall_at_k = {
        k: round(sum(result.hits_at_k[k] / len(result.relevant_ids) for result in results) / len(results), 4)
        for k in cutoffs
    }
    return RetrievalEvaluation(
        total=len(results),
        recall_at_k=recall_at_k,
        mrr=round(sum(result.reciprocal_rank for result in results) / len(results), 4),
        p50_ms=_percentile([result.elapsed_ms for result in results], 0.5),
        p95_ms=_percentile([result.elapsed_ms for result in results], 0.95),
        cases=tuple(results),
    )
