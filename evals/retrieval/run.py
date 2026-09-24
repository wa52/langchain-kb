"""Run the retrieval benchmark on an isolated, hash-pinned example corpus.

Usage: ``python -m evals.retrieval.run``. The child process owns a temporary
Chroma/BM25 index so existing user data and live application singletons are
never opened or modified.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from evals.retrieval.dataset import DEFAULT_CASES_PATH, load_dataset

DEFAULT_REPORT_PATH = Path(__file__).with_name("reports") / "latest.json"


def _isolated_environment(temp_root: Path) -> dict[str, str]:
    env = os.environ.copy()
    for name in ("DEEPSEEK_API_KEY", "LLM_API_KEY", "TYPESAFE_API_KEY", "OPENAI_API_KEY"):
        env.pop(name, None)
    env.update({
        "KNOWLEDGE_HOME": str(temp_root),
        "DATA_DIR": str(temp_root / "docs"),
        "EXTERNAL_DIR": str(temp_root / "external"),
        "CHROMA_PERSIST_DIR": str(temp_root / "chroma"),
        "GRAPH_PERSIST_DIR": str(temp_root / "graph"),
        "CHAT_HISTORY_DIR": str(temp_root / "chat_history"),
        "FILE_TRACKER_PATH": str(temp_root / "file_tracker.json"),
        "CHECKPOINT_DB_PATH": str(temp_root / "checkpoints.sqlite"),
        "MCP_CONFIG_PATH": str(temp_root / "mcp.json"),
        "MCP_ENABLED": "false",
        "ENABLE_GRAPH": "false",
        "ENABLE_GRAPH_LLM_EXTRACTION": "false",
        "ENABLE_HYBRID_SEARCH": "true",
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
        "HF_ENDPOINT": "https://huggingface.co",
        "PYTHONIOENCODING": "utf-8",
    })
    return env


def _atomic_write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _worker(cases_path: Path, output_path: Path) -> int:
    dataset = load_dataset(cases_path)

    # Import configuration and runtime only after the parent has installed the
    # isolated KNOWLEDGE_HOME/CHROMA paths in this child process.
    from config import CHUNK_OVERLAP, CHUNK_SIZE, EMBEDDING_MODEL
    if (CHUNK_SIZE, CHUNK_OVERLAP) != (dataset.chunk_size, dataset.chunk_overlap):
        raise RuntimeError("isolated retrieval config does not match the dataset chunking contract")

    from langchain_core.documents import Document
    from src.application.knowledge import retrieve_scored_documents
    from src.application.retrieval_evaluation import evaluate_retrieval
    from src.ingestion.splitter import create_splitter
    from src.retrieval.retriever import rebuild_bm25
    from src.vector_store.chroma_client import get_vector_store

    splitter = create_splitter(chunk_size=dataset.chunk_size, chunk_overlap=dataset.chunk_overlap)
    documents: list[Document] = []
    for item in dataset.corpus:
        chunks = splitter.split_text(item.path.read_text(encoding="utf-8"))
        for index, content in enumerate(chunks):
            chunk_id = f"{item.source}::{index}"
            documents.append(Document(
                page_content=content,
                metadata={"source": item.source, "chunk_id": chunk_id},
            ))

    available_ids = {doc.metadata["chunk_id"] for doc in documents}
    expected_ids = {
        chunk_id
        for case in dataset.cases
        for chunk_id in case["relevant_ids"]
    }
    missing_ids = sorted(expected_ids - available_ids)
    if missing_ids:
        raise ValueError(f"gold labels reference unknown frozen-corpus chunks: {missing_ids}")

    store = get_vector_store()
    ids = [doc.metadata["chunk_id"] for doc in documents]
    store.add_documents(documents, ids=ids)
    rebuild_bm25(store, echo_fn=lambda *_args, **_kwargs: None)
    metrics = evaluate_retrieval(
        dataset.cases,
        retrieve_scored_documents,
        ks=(1, 3, 5),
    )
    report = {
        "report_version": 1,
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "environment": "isolated-frozen-example-corpus",
        "dataset_version": dataset.schema_version,
        "dataset_sha256": dataset.sha256,
        "retrieval_profile": "src.application.knowledge.retrieve_scored_documents",
        "embedding_model": EMBEDDING_MODEL,
        "chunking": {"size": dataset.chunk_size, "overlap": dataset.chunk_overlap},
        "corpus": [{"source": item.source, "sha256": item.sha256} for item in dataset.corpus],
        "metrics": metrics.snapshot(),
    }
    _atomic_write(output_path, report)
    print(json.dumps({"report": str(output_path), "metrics": metrics.snapshot()}, ensure_ascii=False))
    return 0


def run_isolated(cases_path: Path, output_path: Path) -> int:
    """Spawn an isolated child so all Chroma file handles close before cleanup."""
    load_dataset(cases_path)  # Fail fast on schema/hash errors before model load.
    with tempfile.TemporaryDirectory(prefix="kb-retrieval-eval-") as temp_name:
        temp_root = Path(temp_name)
        env = _isolated_environment(temp_root)
        command = [
            sys.executable,
            str(Path(__file__).resolve()),
            "--worker",
            str(cases_path.resolve()),
            str(output_path.resolve()),
        ]
        completed = subprocess.run(command, cwd=ROOT, env=env, check=False)
        return completed.returncode


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate retrieval on the isolated bundled corpus")
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("_worker_cases", nargs="?", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("_worker_output", nargs="?", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.worker:
        if args._worker_cases is None or args._worker_output is None:
            parser.error("worker mode requires internal cases and output paths")
        return _worker(args._worker_cases, args._worker_output)
    return run_isolated(args.cases, args.output)


if __name__ == "__main__":
    raise SystemExit(main())
