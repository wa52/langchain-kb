from types import SimpleNamespace

from src.application.fast_rag import FastRagService


class _LLM:
    def __init__(self):
        self.calls = []

    def stream(self, messages):
        self.calls.append(messages)
        yield SimpleNamespace(content="标定应先固定相机。")


def _service(retrieve, llm, **overrides):
    return FastRagService(
        retrieve=retrieve,
        llm_factory=lambda: llm,
        token_estimator=lambda text: len(text),
        top_k=overrides.get("top_k", 2),
        fetch_k=overrides.get("fetch_k", 4),
        max_context_tokens=overrides.get("max_context_tokens", 80),
        gate_threshold=overrides.get("gate_threshold", 0.15),
    )


def test_fast_rag_uses_one_llm_call_and_preserves_sources():
    llm = _LLM()
    docs = [SimpleNamespace(page_content="相机标定先固定镜头并采集标定板。", metadata={"source": "标定.md"})]
    service = _service(lambda _query, _k: docs, llm)

    plan = service.prepare([{"role": "user", "content": "相机标定怎么做"}])
    answer = "".join(service.stream_answer([{"role": "user", "content": "相机标定怎么做"}], plan))

    assert plan.relevant is True
    assert plan.llm_calls == 1
    assert len(llm.calls) == 1
    assert "标定.md" in service.citation_suffix(answer, plan.sources)
    assert {"search_ms", "gate_ms", "context_ms", "llm_ms"} <= set(plan.timings)


def test_fast_rag_gate_miss_skips_llm():
    llm = _LLM()
    docs = [SimpleNamespace(page_content="相机标定流程", metadata={"source": "标定.md"})]
    service = _service(lambda _query, _k: docs, llm)

    plan = service.prepare([{"role": "user", "content": "帮我写一封生日邮件"}])

    assert plan.relevant is False
    assert plan.llm_calls == 0
    assert llm.calls == []


def test_fast_rag_context_budget_and_deduplication():
    llm = _LLM()
    docs = [
        SimpleNamespace(page_content="标定" * 100, metadata={"source": "a.md"}),
        SimpleNamespace(page_content="标定" * 100, metadata={"source": "a.md"}),
        SimpleNamespace(page_content="镜头标定" * 100, metadata={"source": "b.md"}),
    ]
    service = _service(lambda _query, _k: docs, llm, top_k=4, max_context_tokens=30)

    plan = service.prepare([{"role": "user", "content": "标定"}])

    assert plan.context_tokens <= 30
    assert plan.selected_docs_count == 1
