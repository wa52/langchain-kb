import json

import pytest

from evals.tools.run import _simulated_jev_request, load_dataset, run_evaluation
from src.application.tool_selection_evaluation import evaluate_tool_cases
from src.harness.jev_selector import JevToolSelector
from src.harness.selector import RuleBasedToolSelector
from src.harness.tools import ToolSpec


def test_tool_selection_metrics_cover_ranks_and_write_exposure():
    cases = [
        {"id": "read", "expected": ["read"], "side_effect": False,
         "write_tool_names": ["write"], "elapsed_ms": 2.0},
        {"id": "write", "expected": ["write"], "side_effect": True,
         "write_tool_names": ["write"], "elapsed_ms": 4.0},
    ]
    chosen = {"read": ["write", "read"], "write": ["write"]}

    result = evaluate_tool_cases(cases, lambda case: chosen[case["id"]])

    assert result["top1_accuracy"] == 0.5
    assert result["top3_recall"] == 1.0
    assert result["write_false_exposure_rate"] == 1.0
    assert result["cases"][0]["first_expected_rank"] == 2
    assert result["latency_ms"] == {"p50": 3.0, "p95": 4.0}


@pytest.mark.parametrize("cases", [[], [{"id": "", "expected": ["x"]}],
                                     [{"id": "x", "expected": []}],
                                     [{"id": "x", "expected": [""]}]])
def test_tool_selection_metrics_reject_invalid_cases(cases):
    with pytest.raises(ValueError):
        evaluate_tool_cases(cases, lambda _case: [])


def test_tool_dataset_is_synthetic_and_hash_pinned():
    dataset, digest = load_dataset()

    assert dataset["schema_version"] == 1
    assert len(dataset["cases"]) == 11
    assert len(digest) == 64
    assert {case["domain"] for case in dataset["cases"]} >= {
        "knowledge", "workflow", "github", "experience",
    }


def test_simulated_jev_does_not_use_expected_labels():
    specs = [
        ToolSpec(name="read_alpha", handler=lambda: None, description="read alpha files", tags=("read",), read_only=True),
        ToolSpec(name="search_beta", handler=lambda: None, description="search beta records", tags=("search",), read_only=True),
    ]
    selector = JevToolSelector(
        RuleBasedToolSelector(max_candidates=2, min_candidates=1),
        api_key="offline-only",
        request=_simulated_jev_request,
    )
    ranked = selector.select_names("search beta records", specs)

    assert ranked[0] == "search_beta"


def test_jev_without_key_does_not_call_provider(monkeypatch):
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    called = []
    specs = [ToolSpec(name="a", handler=lambda: None, description="read a", read_only=True)]
    selector = JevToolSelector(
        RuleBasedToolSelector(max_candidates=1, min_candidates=1),
        request=lambda *_args: called.append(True),
    )

    assert selector.select_names("read a", specs) == ("a",)
    assert called == []


def test_jev_adapter_failure_falls_back_to_rule_selection():
    specs = [ToolSpec(name="a", handler=lambda: None, description="read alpha", read_only=True)]
    fallback = RuleBasedToolSelector(max_candidates=1, min_candidates=1)
    selector = JevToolSelector(
        fallback,
        api_key="synthetic-test-key",
        request=lambda *_args: (_ for _ in ()).throw(RuntimeError("simulated failure")),
    )

    assert selector.select_names("read alpha", specs) == fallback.select_names("read alpha", specs)


def test_evaluation_ignores_configured_jev_key_and_writes_offline_report(tmp_path, monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "must-not-be-used-or-written")
    output = tmp_path / "latest.json"

    report = run_evaluation(output_path=output)
    serialized = output.read_text(encoding="utf-8")

    assert report["external_provider_called"] is False
    assert report["results"]["jev_simulated"]["total"] == 11
    assert "must-not-be-used-or-written" not in serialized
    assert "offline-simulation-only" not in serialized
    assert json.loads(serialized)["dataset_sha256"] == report["dataset_sha256"]


def test_bad_dataset_with_unknown_expected_tool_is_rejected(tmp_path):
    path = tmp_path / "cases.json"
    path.write_text(json.dumps({"schema_version": 1, "tools": [{"name": "a"}],
                               "cases": [{"id": "bad", "query": "x", "expected": ["missing"]}]}),
                    encoding="utf-8")

    with pytest.raises(ValueError, match="unknown expected"):
        load_dataset(path)
