import json
from pathlib import Path

from langchain_core.documents import Document

from src.application.routing_evaluation import evaluate_routes
from src.application.smart_router import SmartRouteService
from src.domain.routing import Route, ScoredDocument


CASES_PATH = Path(__file__).with_name("fixtures") / "routing_cases.json"


def _retriever(query: str, _limit: int):
    # The corpus declares retrieval conditions separately from the expected route,
    # so this benchmark covers routing policy without external Chroma/LLM variance.
    case = next(case for case in _cases() if case["query"] == query)
    if case["retrieval"] != "strong":
        return []
    return [
        ScoredDocument(Document(page_content=query + " 技术资料"), dense_score=0.93, bm25_score=1.0, fusion_score=0.93, dense_rank=1, bm25_rank=1, final_rank=1),
        ScoredDocument(Document(page_content=query + " 项目方案"), dense_score=0.84, bm25_score=0.5, fusion_score=0.84, dense_rank=2, bm25_rank=2, final_rank=2),
    ]


def _cases():
    return json.loads(CASES_PATH.read_text(encoding="utf-8"))


def test_routing_corpus_has_balanced_100_labelled_cases():
    cases = _cases()
    assert len(cases) == 100
    assert {case["expected"] for case in cases} == {route.value for route in Route}
    counts = {route.value: sum(case["expected"] == route.value for case in cases) for route in Route}
    assert all(count >= 30 for count in counts.values())


def test_smart_router_meets_routing_evaluation_baseline():
    router = SmartRouteService(_retriever, fetch_k=4, rag_threshold=0.55)
    report = evaluate_routes(_cases(), lambda query: router.decide(query, []).route)
    assert report.total == 100
    assert report.macro_f1 >= 0.98
    assert report.per_route[Route.FAST_RAG.value]["recall"] >= 0.98
    assert report.per_route[Route.AGENT.value]["recall"] >= 0.98
    assert report.false_rag_rate <= 0.01
