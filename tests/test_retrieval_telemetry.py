from types import SimpleNamespace
from unittest.mock import patch


def test_retrieval_record_contains_stage_timings_and_counts():
    import src.agent.tools as tools
    from src.retrieval.telemetry import retrieval_record_store

    document = SimpleNamespace(page_content="标定步骤", metadata={"source": "guide.md"})
    retrieval_record_store.clear()
    tools._retrieve_knowledge_cached.cache_clear()
    try:
        with (
            patch.object(tools, "_search", return_value=[document]),
            patch.object(tools, "ENABLE_GRADING", False),
            patch.object(tools, "ENABLE_CONTEXT_COMPRESSION", False),
            patch.object(tools, "ENABLE_GRAPH", False),
        ):
            result = tools._retrieve_knowledge_cached("相机标定", None, 1)
    finally:
        tools._retrieve_knowledge_cached.cache_clear()

    assert "guide.md" in result
    records = retrieval_record_store.recent(1)
    assert len(records) == 1
    record = records[0]
    assert record["status"] == "completed"
    assert record["cache_hit"] is False
    assert record["raw_docs_count"] == 1
    assert record["selected_docs_count"] == 1
    assert {"search_ms", "grading_ms", "compression_ms"} <= set(record["stages"])


def test_retrieval_record_store_is_bounded_and_returns_newest_first():
    from src.retrieval.telemetry import RetrievalRecord, RetrievalRecordStore

    store = RetrievalRecordStore(max_records=2)
    for query in ("一", "二", "三"):
        store.put(RetrievalRecord(query=query))
    assert [item["query"] for item in store.recent(10)] == ["三", "二"]
    assert store.get("missing") is None


def test_cached_retrieval_adds_a_cache_hit_record():
    import src.agent.tools as tools
    from src.retrieval.telemetry import retrieval_record_store

    document = SimpleNamespace(page_content="标定步骤", metadata={"source": "guide.md"})
    tools.clear_retrieval_cache()
    retrieval_record_store.clear()
    try:
        with (
            patch.object(tools, "_search", return_value=[document]),
            patch.object(tools, "ENABLE_GRADING", False),
            patch.object(tools, "ENABLE_CONTEXT_COMPRESSION", False),
            patch.object(tools, "ENABLE_GRAPH", False),
        ):
            tools.retrieve_knowledge.invoke({"query": "相机标定"})
            tools.retrieve_knowledge.invoke({"query": "相机标定"})
    finally:
        tools.clear_retrieval_cache()

    records = retrieval_record_store.recent(2)
    assert records[0]["cache_hit"] is True
    assert records[0]["stages"] == {}
