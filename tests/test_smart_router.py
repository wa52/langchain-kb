from types import SimpleNamespace

from src.application.smart_router import SmartRouteService
from src.domain.routing import Route


def _router(documents):
    return SmartRouteService(lambda _query, _k: documents, fetch_k=8, rag_threshold=0.2)


def test_smart_router_hard_routes_mutating_and_tool_requests_to_agent():
    decision = _router([]).decide("帮我创建一个 GitHub issue", [])
    assert decision.route == Route.AGENT
    assert "tool_or_side_effect_intent" in decision.reasons


def test_smart_router_routes_relevant_knowledge_to_fast_rag_with_signals():
    docs = [SimpleNamespace(page_content="HALCON 异常检测模型训练和阈值设置方案", metadata={})]
    decision = _router(docs).decide("异常检测模型怎么训练", [])
    assert decision.route == Route.FAST_RAG
    assert decision.signals["hit_count"] == 1
    assert "retrieval_semantic_hit" in decision.reasons


def test_smart_router_routes_low_confidence_request_to_direct():
    docs = [SimpleNamespace(page_content="HALCON 标定流程", metadata={})]
    decision = _router(docs).decide("今天适合喝什么咖啡", [])
    assert decision.route == Route.DIRECT


def test_smart_router_uses_fast_rag_history_for_short_follow_up():
    docs = [SimpleNamespace(page_content="HALCON 第二种异常检测方案", metadata={})]
    history = [
        {"role": "user", "content": "HALCON 异常检测训练参数"},
        {"role": "assistant", "content": "资料回答", "route": "fast_rag"},
    ]
    decision = _router(docs).decide("第二种呢？", history)
    assert decision.route == Route.FAST_RAG
    assert decision.signals["context"] == 1.0
