"""Metrics for a synthetic, offline tool-selection benchmark."""

from __future__ import annotations

from dataclasses import dataclass
from statistics import median
from typing import Iterable


@dataclass(frozen=True)
class ToolCaseResult:
    case_id: str
    expected: tuple[str, ...]
    selected: tuple[str, ...]
    first_expected_rank: int | None
    top1_hit: bool
    top3_hit: bool
    false_write_exposure: tuple[str, ...]
    elapsed_ms: float


def evaluate_tool_cases(cases: Iterable[dict], selector) -> dict:
    """Evaluate a selector callable returning ordered tool names per case."""
    items = list(cases)
    if not items:
        raise ValueError("tool evaluation requires at least one case")
    ids = [str(item.get("id", "")).strip() for item in items]
    if any(not case_id for case_id in ids) or len(set(ids)) != len(ids):
        raise ValueError("tool evaluation case IDs must be non-empty and unique")
    results: list[ToolCaseResult] = []
    for case in items:
        expected = tuple(dict.fromkeys(case.get("expected", ())))
        if not expected:
            raise ValueError(f"case {case['id']} must have expected tool IDs")
        if any(not isinstance(name, str) or not name for name in expected):
            raise ValueError(f"case {case['id']} has an invalid expected tool ID")
        selected = tuple(dict.fromkeys(selector(case)))
        first = next((index for index, name in enumerate(selected, 1) if name in expected), None)
        expected_side_effect = bool(case.get("side_effect", False))
        writes = tuple(case.get("write_tool_names", ()))
        exposed = tuple(name for name in selected if name in writes) if not expected_side_effect else ()
        results.append(ToolCaseResult(
            case_id=case["id"], expected=expected, selected=selected,
            first_expected_rank=first,
            top1_hit=bool(selected and selected[0] in expected),
            top3_hit=any(name in expected for name in selected[:3]),
            false_write_exposure=exposed,
            elapsed_ms=round(max(0.0, float(case.get("elapsed_ms", 0.0))), 3),
        ))
    latencies = sorted(item.elapsed_ms for item in results)
    p95_index = max(0, min(len(latencies) - 1, int(0.95 * len(latencies) + 0.999) - 1))
    write_opportunities = sum(not bool(item.get("side_effect", False)) for item in items)
    false_exposures = sum(bool(result.false_write_exposure) for result in results)
    return {
        "total": len(results),
        "top1_accuracy": round(sum(item.top1_hit for item in results) / len(results), 4),
        "top3_recall": round(sum(item.top3_hit for item in results) / len(results), 4),
        "write_false_exposure_rate": round(false_exposures / write_opportunities, 4) if write_opportunities else 0.0,
        "write_false_exposure_cases": false_exposures,
        "latency_ms": {"p50": round(median(latencies), 3), "p95": round(latencies[p95_index], 3)},
        "cases": [
            {"case_id": item.case_id, "expected": list(item.expected), "selected": list(item.selected),
             "first_expected_rank": item.first_expected_rank, "top1_hit": item.top1_hit,
             "top3_hit": item.top3_hit, "false_write_exposure": list(item.false_write_exposure),
             "elapsed_ms": item.elapsed_ms}
            for item in results
        ],
    }
