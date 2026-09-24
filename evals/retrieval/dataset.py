"""Versioned, hash-pinned retrieval evaluation data loader."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

EVALS_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CASES_PATH = Path(__file__).with_name("cases.json")


@dataclass(frozen=True)
class CorpusFile:
    source: str
    path: Path
    sha256: str


@dataclass(frozen=True)
class RetrievalDataset:
    schema_version: int
    top_k: int
    chunk_size: int
    chunk_overlap: int
    corpus: tuple[CorpusFile, ...]
    cases: tuple[dict[str, Any], ...]
    sha256: str


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def load_dataset(path: Path = DEFAULT_CASES_PATH) -> RetrievalDataset:
    """Load a benchmark only when its schema, paths, hashes and IDs are valid."""
    path = path.resolve()
    try:
        raw_bytes = path.read_bytes()
        data = json.loads(raw_bytes)
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"unable to read retrieval dataset: {exc}") from exc
    if not isinstance(data, Mapping) or data.get("schema_version") != 1:
        raise ValueError("retrieval dataset schema_version must be 1")

    top_k = data.get("top_k")
    chunk_size = data.get("chunk_size")
    chunk_overlap = data.get("chunk_overlap")
    if not isinstance(top_k, int) or top_k < 5:
        raise ValueError("retrieval dataset top_k must be an integer >= 5")
    if not isinstance(chunk_size, int) or chunk_size < 1:
        raise ValueError("chunk_size must be a positive integer")
    if not isinstance(chunk_overlap, int) or not 0 <= chunk_overlap < chunk_size:
        raise ValueError("chunk_overlap must be in [0, chunk_size)")

    corpus_data = data.get("corpus")
    cases = data.get("cases")
    if not isinstance(corpus_data, list) or not corpus_data:
        raise ValueError("retrieval dataset requires a non-empty corpus")
    if not isinstance(cases, list) or not cases:
        raise ValueError("retrieval dataset requires non-empty cases")

    corpus: list[CorpusFile] = []
    seen_sources: set[str] = set()
    corpus_root = EVALS_ROOT.resolve()
    for item in corpus_data:
        if not isinstance(item, Mapping):
            raise ValueError("each corpus entry must be an object")
        source = str(item.get("source", "")).strip()
        relative_path = str(item.get("path", "")).strip()
        expected_hash = str(item.get("sha256", "")).lower()
        if not source or source in seen_sources or not relative_path:
            raise ValueError(f"invalid or duplicate corpus source: {source or '<empty>'}")
        corpus_path = (path.parent / relative_path).resolve()
        if not corpus_path.is_relative_to(corpus_root):
            raise ValueError(f"corpus path must remain under {corpus_root}")
        try:
            content = corpus_path.read_bytes()
        except OSError as exc:
            raise ValueError(f"unable to read corpus source {source}: {exc}") from exc
        actual_hash = _sha256(content)
        if actual_hash != expected_hash:
            raise ValueError(f"corpus hash mismatch for {source}")
        seen_sources.add(source)
        corpus.append(CorpusFile(source, corpus_path, actual_hash))

    from src.application.retrieval_evaluation import _validated_cases

    normalized_cases = _validated_cases(cases)
    case_ids = {item[0] for item in normalized_cases}
    if len(case_ids) != len(cases):
        raise ValueError("retrieval case ids must be unique")
    return RetrievalDataset(
        schema_version=1,
        top_k=top_k,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        corpus=tuple(corpus),
        cases=tuple(dict(case) for case in cases),
        sha256=_sha256(raw_bytes),
    )
