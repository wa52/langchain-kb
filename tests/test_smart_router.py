from types import SimpleNamespace

import pytest

from src.application.smart_router import SmartRouteService
from src.domain.routing import Route, ScoredDocument


def _router(documents):
    return SmartRouteService(lambda _query, _k: documents, fetch_k=8, rag_threshold=0.2)


def _scored(text, *, dense=0.9, bm25=1.0):
    return ScoredDocument(SimpleNamespace(page_content=text, metadata={}), dense_score=dense, bm25_score=bm25, fusion_score=(dense + bm25) / 2, dense_rank=1, bm25_rank=1, final_rank=1)


def test_smart_router_hard_routes_mutating_and_tool_requests_to_agent():
    decision = _router([]).decide("帮我创建一个 GitHub issue", [])
    assert decision.route == Route.AGENT
    assert "tool_or_side_effect_intent" in decision.reasons


def test_smart_router_routes_relevant_knowledge_to_fast_rag_with_signals():
    docs = [_scored("HALCON 异常检测模型训练和阈值设置方案")]
    decision = _router(docs).decide("异常检测模型怎么训练", [])
    assert decision.route == Route.FAST_RAG
    assert decision.signals["hit_count"] == 1
    assert "retrieval_semantic_hit" in decision.reasons


def test_smart_router_routes_low_confidence_request_to_direct():
    docs = [_scored("HALCON 标定流程", dense=0.1, bm25=0.0)]
    decision = _router(docs).decide("今天适合喝什么咖啡", [])
    assert decision.route == Route.DIRECT


def test_smart_router_uses_fast_rag_history_for_short_follow_up():
    docs = [_scored("HALCON 第二种异常检测方案")]
    history = [
        {"role": "user", "content": "HALCON 异常检测训练参数"},
        {"role": "assistant", "content": "资料回答", "route": "fast_rag"},
    ]
    decision = _router(docs).decide("第二种呢？", history)
    assert decision.route == Route.FAST_RAG
    assert decision.signals["context"] == 1.0


def test_smart_router_does_not_inherit_an_unrelated_short_follow_up():
    docs = [_scored("HALCON 第二种异常检测方案")]
    history = [
        {"role": "user", "content": "HALCON 异常检测训练参数"},
        {"role": "assistant", "content": "资料回答", "route": "fast_rag"},
    ]
    router = SmartRouteService(
        lambda _query, _k: docs, fetch_k=8, rag_threshold=0.2,
        topic_similarity=lambda _current, _previous: 0.1,
    )
    decision = router.decide("那今天吃什么？", history)
    assert decision.signals["context"] == 0.0
    assert decision.signals["context_topic_similarity"] == 0.1


@pytest.mark.parametrize("query", [
    "我那个异常检测模型最后保存成什么文件名",
    "之前相机实时推理准备多久保存一次图片",
])
def test_smart_router_keeps_historical_save_questions_on_the_rag_path(query):
    decision = _router([_scored(query)]).decide(query, [])
    assert decision.route == Route.FAST_RAG


@pytest.mark.parametrize("query", [
    "请去 GitHub 看一下这个项目最新的 commit",
    "去网页搜索 BEIR 的官方评测指标",
])
def test_smart_router_recognizes_external_reading_actions(query):
    decision = _router([]).decide(query, [])
    assert decision.route == Route.AGENT


@pytest.mark.parametrize("query", [
    "保存文件时为什么要用原子写入",
    "创建 issue 通常需要哪些字段",
])
def test_smart_router_keeps_action_concept_questions_direct(query):
    assert _router([]).decide(query, []).route == Route.DIRECT


def test_smart_router_allows_personal_action_concepts_to_use_rag():
    query = "以前的聊天执行链为什么要从 API 层迁走"
    assert _router([_scored(query)]).decide(query, []).route == Route.FAST_RAG


@pytest.mark.parametrize("query", [
    "用 MCP 获取当前知识库健康状态",
    "请新建一个 issue 来追踪这个错误",
])
def test_smart_router_recognizes_colloquial_tool_commands(query):
    assert _router([]).decide(query, []).route == Route.AGENT
