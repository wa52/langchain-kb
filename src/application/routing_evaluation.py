"""Small, dependency-free metrics for the Smart Routing evaluation corpus."""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

from src.domain.routing import Route


@dataclass(frozen=True)
class RoutingEvaluation:
    total: int
    accuracy: float
    macro_f1: float
    per_route: dict[str, dict[str, float]]
    confusion: dict[str, dict[str, int]]
    false_rag_rate: float

    def snapshot(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "accuracy": self.accuracy,
            "macro_f1": self.macro_f1,
            "per_route": self.per_route,
            "confusion": self.confusion,
            "false_rag_rate": self.false_rag_rate,
        }


def evaluate_routes(cases: Iterable[dict[str, Any]], decide: Callable[[str], Route]) -> RoutingEvaluation:
    """Evaluate a route decision function against explicitly labelled cases."""
    labels = tuple(Route)
    confusion = {expected.value: {actual.value: 0 for actual in labels} for expected in labels}
    total = correct = false_rag = non_rag = 0
    for case in cases:
        expected = Route(str(case["expected"]))
        actual = Route(decide(str(case["query"])))
        confusion[expected.value][actual.value] += 1
        total += 1
        correct += actual == expected
        if expected is not Route.FAST_RAG:
            non_rag += 1
            false_rag += actual is Route.FAST_RAG

    per_route: dict[str, dict[str, float]] = {}
    f1_values = []
    for route in labels:
        name = route.value
        true_positive = confusion[name][name]
        false_positive = sum(confusion[other.value][name] for other in labels if other is not route)
        false_negative = sum(confusion[name][other.value] for other in labels if other is not route)
        precision = true_positive / (true_positive + false_positive) if true_positive + false_positive else 0.0
        recall = true_positive / (true_positive + false_negative) if true_positive + false_negative else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        per_route[name] = {"precision": round(precision, 4), "recall": round(recall, 4), "f1": round(f1, 4)}
        f1_values.append(f1)
    return RoutingEvaluation(
        total=total,
        accuracy=round(correct / total, 4) if total else 0.0,
        macro_f1=round(sum(f1_values) / len(f1_values), 4) if f1_values else 0.0,
        per_route=per_route,
        confusion=confusion,
        false_rag_rate=round(false_rag / non_rag, 4) if non_rag else 0.0,
    )
