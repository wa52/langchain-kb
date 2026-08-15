from unittest.mock import MagicMock, patch
import json

import pytest

from src.graph_store.extraction_llm import extract_entities_llm_batch, _parse_llm_response, _validate_entities


class MockResponse:
    def __init__(self, content):
        self.content = content


MOCK_LLM_OK = MagicMock()
MOCK_LLM_OK.invoke = MagicMock(return_value=MockResponse(
    json.dumps({
        "entities": [
            {"name": "LangChain", "type": "Framework"},
            {"name": "RAG", "type": "Concept"},
        ],
        "relations": [
            {"source": "LangChain", "target": "RAG", "relation": "supports"},
        ],
    }, ensure_ascii=False)
))

MOCK_LLM_WRAPPED = MagicMock()
MOCK_LLM_WRAPPED.invoke = MagicMock(return_value=MockResponse(
    "```json\n" + json.dumps({
        "entities": [{"name": "Agent", "type": "Tool"}],
        "relations": [],
    }, ensure_ascii=False) + "\n```"
))

MOCK_LLM_FAIL = MagicMock()
MOCK_LLM_FAIL.invoke = MagicMock(side_effect=Exception("API quota exceeded"))


class TestParseLlmResponse:
    def test_plain_json(self):
        result = _parse_llm_response('{"entities": []}')
        assert result == {"entities": []}

    def test_wrapped_json(self):
        result = _parse_llm_response('```json\n{"entities": []}\n```')
        assert result == {"entities": []}

    def test_wrapped_no_label(self):
        result = _parse_llm_response('```\n{"entities": []}\n```')
        assert result == {"entities": []}


class TestValidateEntities:
    def test_valid_type_passes(self):
        data = {"entities": [{"name": "LangChain", "type": "Framework"}], "relations": []}
        result = _validate_entities(data)
        assert result["entities"][0]["type"] == "Framework"

    def test_invalid_type_becomes_unknown(self):
        data = {"entities": [{"name": "LangChain", "type": "CoolLibrary"}], "relations": []}
        result = _validate_entities(data)
        assert result["entities"][0]["type"] == "Unknown"

    def test_empty_name_skipped(self):
        data = {"entities": [{"name": "", "type": "Framework"}], "relations": []}
        result = _validate_entities(data)
        assert len(result["entities"]) == 0


class TestExtractEntitiesLlmBatch:

    def test_llm_extraction_normal(self):
        entities, relations = extract_entities_llm_batch(
            ["LangChain is a framework. RAG is a concept."],
            llm=MOCK_LLM_OK,
        )
        names = [e["name"] for e in entities]
        assert "LangChain" in names
        assert "RAG" in names
        assert len(relations) == 1

    def test_llm_extraction_wrapped_json(self):
        entities, relations = extract_entities_llm_batch(
            ["Agent is a tool."],
            llm=MOCK_LLM_WRAPPED,
        )
        names = [e["name"] for e in entities]
        assert "Agent" in names

    def test_llm_fallback_to_jieba(self):
        entities, _ = extract_entities_llm_batch(
            ["LangChain Agent 可以自主决策。LangChain Agent 可以使用工具。LangChain Agent 有多种类型。"],
            llm=MOCK_LLM_FAIL,
        )
        names = [e["name"] for e in entities]
        assert "LangChain" in names

    def test_multiple_batches_all_merged(self):
        """Every batch is processed and merged once (batch size 10 over 25 texts)."""
        texts = [f"LangChain 第 {i} 段使用 RAG 框架。" for i in range(1, 26)]
        llm = MagicMock()
        llm.invoke = MagicMock(return_value=MockResponse(json.dumps({
            "entities": [{"name": "LangChain", "type": "Framework"}],
            "relations": [],
        }, ensure_ascii=False)))
        with patch("config.GRAPH_LLM_BATCH_SIZE", 10):
            entities, _ = extract_entities_llm_batch(texts, llm=llm)
        names = [e["name"] for e in entities]
        assert "LangChain" in names
        # 25 texts / batch 10 => 3 batches, all invoked
        assert llm.invoke.call_count == 3

    def test_parallel_batch_failure_falls_back_per_batch(self):
        """A failing batch falls back to jieba while other batches still use LLM."""
        jieba_text = "B2标记。LangChain Agent 可以自主决策。LangChain Agent 可以使用工具。LangChain Agent 有多种类型。"
        texts = (
            ["B1段 LangChain 使用 RAG。"] * 10
            + [jieba_text] * 10
            + ["B3段 LangChain 使用 API。"] * 5
        )
        llm = MagicMock()

        def invoke(prompt):
            if "B2标记" in prompt:
                raise Exception("batch failed")
            return MockResponse(json.dumps({
                "entities": [{"name": "RAG", "type": "Concept"}],
                "relations": [],
            }, ensure_ascii=False))

        llm.invoke = MagicMock(side_effect=invoke)
        with patch("config.GRAPH_LLM_BATCH_SIZE", 10):
            entities, _ = extract_entities_llm_batch(texts, llm=llm)
        names = [e["name"] for e in entities]
        assert "LangChain" in names  # jieba fallback ran for the failed batch
        assert "RAG" in names  # LLM succeeded for the other batches
