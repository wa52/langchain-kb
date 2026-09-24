from pathlib import Path
from types import SimpleNamespace

import pytest

from src.application.retrieval_evaluation import evaluate_retrieval
from evals.retrieval.dataset import load_dataset
from evals.retrieval.run import _atomic_write, _isolated_environment


def candidate(chunk_id: str):
    return SimpleNamespace(metadata={"chunk_id": chunk_id})


def test_retrieval_evaluation_reports_recall_mrr_and_case_ranks():
    cases = [
        {"id": "case-a", "query": "query a", "relevant_ids": ["a"]},
        {"id": "case-b", "query": "query b", "relevant_ids": ["c", "d"]},
    ]
    ranked = {
        "query a": [candidate("x"), candidate("a"), candidate("z")],
        "query b": [candidate("d"), candidate("x"), candidate("c")],
    }

    report = evaluate_retrieval(cases, lambda query, _limit: ranked[query], ks=(1, 3))

    assert report.total == 2
    assert report.recall_at_k == {1: 0.25, 3: 1.0}
    assert report.mrr == 0.75
    assert report.cases[0].first_relevant_rank == 2
    assert report.cases[1].first_relevant_rank == 1
    assert report.cases[0].hits_at_k == {1: 0, 3: 1}


def test_retrieval_evaluation_counts_empty_results_as_misses():
    report = evaluate_retrieval(
        [{"id": "empty", "query": "unmatched", "relevant_ids": ["wanted"]}],
        lambda _query, _limit: [],
    )

    assert report.recall_at_k[5] == 0.0
    assert report.mrr == 0.0
    assert report.cases[0].first_relevant_rank is None


def test_bundled_dataset_is_hash_pinned_and_chunk_labels_exist():
    from src.ingestion.splitter import create_splitter

    dataset = load_dataset()
    actual_ids = set()
    splitter = create_splitter(dataset.chunk_size, dataset.chunk_overlap)
    for item in dataset.corpus:
        chunks = splitter.split_text(item.path.read_text(encoding="utf-8"))
        actual_ids.update(f"{item.source}::{index}" for index in range(len(chunks)))
    expected_ids = {
        chunk_id
        for case in dataset.cases
        for chunk_id in case["relevant_ids"]
    }

    assert dataset.schema_version == 1
    assert len(dataset.cases) == 14
    assert expected_ids <= actual_ids
    assert {case["category"] for case in dataset.cases} >= {
        "natural_language", "operator_names", "code_example", "paraphrase",
    }


def test_isolated_runner_never_inherits_llm_credentials_or_uses_project_data(tmp_path, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "must-not-cross-process-boundary")
    monkeypatch.setenv("TYPESAFE_API_KEY", "must-not-cross-process-boundary")

    env = _isolated_environment(tmp_path)

    assert "DEEPSEEK_API_KEY" not in env
    assert "TYPESAFE_API_KEY" not in env
    assert env["HF_HUB_OFFLINE"] == "1"
    assert Path(env["CHROMA_PERSIST_DIR"]).is_relative_to(tmp_path)
    assert Path(env["KNOWLEDGE_HOME"]) == tmp_path


def test_report_writer_publishes_complete_json_atomically(tmp_path):
    report_path = tmp_path / "nested" / "latest.json"
    payload = {"metrics": {"recall_at_k": {"5": 0.9}}, "cases": [{"case_id": "case-a"}]}

    _atomic_write(report_path, payload)

    import json
    assert json.loads(report_path.read_text(encoding="utf-8")) == payload
    assert not report_path.with_suffix(".json.tmp").exists()


@pytest.mark.parametrize(
    "cases",
    [
        [],
        [{"id": "same", "query": "a", "relevant_ids": ["x"]}, {"id": "same", "query": "b", "relevant_ids": ["y"]}],
        [{"id": "missing-label", "query": "a", "relevant_ids": []}],
        [{"id": "blank-query", "query": "  ", "relevant_ids": ["x"]}],
    ],
)
def test_retrieval_evaluation_rejects_invalid_cases(cases):
    with pytest.raises(ValueError):
        evaluate_retrieval(cases, lambda _query, _limit: [])
