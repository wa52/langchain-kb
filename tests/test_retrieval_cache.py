from types import SimpleNamespace
from concurrent.futures import ThreadPoolExecutor
import time
from unittest.mock import patch


def test_identical_retrieval_reuses_cached_evidence_until_index_changes():
    from src.agent.tools import clear_retrieval_cache, retrieve_knowledge

    document = SimpleNamespace(page_content="标定步骤", metadata={"source": "guide.md"})
    versions = iter([7, 7, 8])
    clear_retrieval_cache()
    try:
        with (
            patch("src.agent.tools._index_version", side_effect=lambda: next(versions)),
            patch("src.agent.tools._search", return_value=[document]) as search,
            patch("src.agent.tools.ENABLE_GRADING", False),
            patch("src.agent.tools.ENABLE_CONTEXT_COMPRESSION", False),
            patch("src.agent.tools.ENABLE_GRAPH", False),
        ):
            first = retrieve_knowledge.invoke({"query": "  相机   标定  "})
            second = retrieve_knowledge.invoke({"query": "相机 标定"})
            third = retrieve_knowledge.invoke({"query": "相机 标定"})
    finally:
        clear_retrieval_cache()

    assert first == second == third
    assert search.call_count == 2


def test_concurrent_identical_queries_share_one_retrieval():
    from src.agent.tools import clear_retrieval_cache, retrieve_knowledge

    document = SimpleNamespace(page_content="标定步骤", metadata={"source": "guide.md"})

    def slow_search(*_args, **_kwargs):
        time.sleep(0.05)
        return [document]

    clear_retrieval_cache()
    try:
        with (
            patch("src.agent.tools._index_version", return_value=3),
            patch("src.agent.tools._search", side_effect=slow_search) as search,
            patch("src.agent.tools.ENABLE_GRADING", False),
            patch("src.agent.tools.ENABLE_CONTEXT_COMPRESSION", False),
            patch("src.agent.tools.ENABLE_GRAPH", False),
        ):
            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(
                    lambda _n: retrieve_knowledge.invoke({"query": "相机标定"}),
                    range(2),
                ))
    finally:
        clear_retrieval_cache()

    assert results[0] == results[1]
    assert search.call_count == 1
