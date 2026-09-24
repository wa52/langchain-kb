"""Run Rule and simulated-Jev selection on synthetic cases; no network calls."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter

from src.application.tool_selection_evaluation import evaluate_tool_cases
from src.harness.jev_selector import JevToolSelector
from src.harness.selector import RuleBasedToolSelector, ToolSelectionContext
from src.harness.tools import ToolSpec

ROOT = Path(__file__).resolve().parents[2]
DATASET_PATH = Path(__file__).with_name("cases.json")
REPORT_PATH = Path(__file__).with_name("reports") / "latest.json"


def load_dataset(path: Path = DATASET_PATH) -> tuple[dict, str]:
    raw = path.read_bytes()
    dataset = json.loads(raw)
    if dataset.get("schema_version") != 1 or not dataset.get("cases"):
        raise ValueError("unsupported or empty tool-selection dataset")
    names = [tool.get("name", "") for tool in dataset.get("tools", [])]
    if not names or len(names) != len(set(names)):
        raise ValueError("tool names must be non-empty and unique")
    name_set = set(names)
    case_ids: set[str] = set()
    for case in dataset["cases"]:
        case_id = str(case.get("id", "")).strip()
        if not case_id or case_id in case_ids:
            raise ValueError("case IDs must be non-empty and unique")
        case_ids.add(case_id)
        if not str(case.get("query", "")).strip() or not set(case.get("expected", ())) <= name_set:
            raise ValueError(f"invalid query or unknown expected tool in case {case_id}")
        if not case.get("expected"):
            raise ValueError(f"case {case_id} must include expected tools")
    return dataset, hashlib.sha256(raw).hexdigest()


def _specs(dataset: dict) -> tuple[ToolSpec, ...]:
    return tuple(ToolSpec(
        name=item["name"], handler=lambda **_kwargs: None,
        description=item.get("description", ""), source="local",
        tags=tuple(item.get("tags", ())), read_only=bool(item.get("read_only", True)),
        enabled=True,
    ) for item in dataset["tools"])


def _context(case: dict) -> ToolSelectionContext:
    return ToolSelectionContext(
        intent=case["intent"], domain=case.get("domain", "general"),
        side_effect=bool(case.get("side_effect", False)),
    )


_WORD = re.compile(r"[a-z0-9_]+|[\u4e00-\u9fff]")


def _simulated_jev_request(payload: dict, _simulation_marker: str) -> dict:
    """Deterministically rank adapter candidates by query/description token overlap.

    This deliberately does not use expected labels and is not a proxy for Jev
    model quality; it validates adapter/report flow only.
    """
    query_tokens = set(_WORD.findall(payload["state"]["user_request"].lower()))
    criteria = payload["questions"]["tool"]["criteria"]
    weights = {}
    for name, description in criteria.items():
        tokens = set(_WORD.findall(f"{name} {description}".lower()))
        weights[name] = 1 + len(query_tokens & tokens)
    total = sum(weights.values()) or 1
    return {"answers": {"tool": {"probabilities": {name: weight / total for name, weight in weights.items()}}}}


def run_evaluation(dataset_path: Path = DATASET_PATH, output_path: Path = REPORT_PATH) -> dict:
    dataset, dataset_hash = load_dataset(dataset_path)
    specs = _specs(dataset)
    writes = {item.name for item in specs if not item.read_only}
    rule = RuleBasedToolSelector(max_candidates=len(specs), min_candidates=min(3, len(specs)))
    simulated_jev = JevToolSelector(rule, api_key="offline-simulation-only", request=_simulated_jev_request)

    def measure(selector):
        measured = []
        for case in dataset["cases"]:
            started = perf_counter()
            names = selector.select_names(case["query"], specs, context=_context(case))
            elapsed_ms = (perf_counter() - started) * 1000
            measured.append({**case, "write_tool_names": sorted(writes), "elapsed_ms": elapsed_ms,
                             "selected_names": list(names)})
        return evaluate_tool_cases(measured, lambda item: item["selected_names"])

    report = {
        "report_version": 1,
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "environment": "synthetic-offline",
        "provider_mode": {"rule": "deterministic-rule-based", "jev": "simulated-local-adapter"},
        "dataset_version": dataset["schema_version"],
        "dataset_sha256": dataset_hash,
        "external_provider_called": False,
        "results": {
            "rule": measure(rule),
            "jev_simulated": measure(simulated_jev),
        },
        "limitations": "Jev mode is a deterministic local adapter simulation, not a real Jev model evaluation.",
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(output_path.suffix + ".tmp")
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(output_path)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run synthetic offline tool selection evaluation")
    parser.add_argument("--cases", type=Path, default=DATASET_PATH)
    parser.add_argument("--output", type=Path, default=REPORT_PATH)
    args = parser.parse_args(argv)
    report = run_evaluation(args.cases, args.output)
    summary = {name: {key: value for key, value in result.items() if key != "cases"}
               for name, result in report["results"].items()}
    print(json.dumps({"report": str(args.output), "dataset_sha256": report["dataset_sha256"], "results": summary}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
