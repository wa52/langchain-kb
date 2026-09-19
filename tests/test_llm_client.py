from unittest.mock import patch

import config
from src.llm import client


def _make_llm(*, provider: str, model: str):
    with (
        patch.object(config, "LLM_PROVIDER", provider),
        patch.object(config, "LLM_MODEL", model),
        patch.object(config, "LLM_API_KEY", "test-key"),
        patch.object(config, "LLM_API_BASE", "https://example.test/v1"),
    ):
        client.get_llm.cache_clear()
        return client.get_llm()


def test_zhipu_glm_53_uses_low_reasoning_effort_and_bounded_timeout():
    llm = _make_llm(provider="zhipu", model="glm-5.3-flash")

    assert llm.reasoning_effort == "low"
    assert llm.request_timeout == 90.0
    assert llm.stream_chunk_timeout == 45.0


def test_other_providers_keep_their_existing_reasoning_behavior():
    llm = _make_llm(provider="deepseek", model="deepseek-chat")

    assert llm.reasoning_effort is None
    assert llm.request_timeout == 90.0
    assert llm.stream_chunk_timeout == 45.0
