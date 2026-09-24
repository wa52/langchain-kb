# Loop 003 — Retrieval Quality Evaluation Runner

**Outcome:** PASS (fixture/harness scope only)

## Delivered

- Versioned, hash-pinned 14-query dataset over four repository-owned documents.
- Isolated runner uses the existing `retrieve_scored_documents` seam, a
  temporary `KNOWLEDGE_HOME`/Chroma index, offline embeddings, and no LLM/MCP
  credentials. It does not touch the running service or personal corpus.
- Deterministic Recall@K/MRR, per-case relevant ranks, latency percentiles, and
  an atomic JSON report.
- `GET /api/v1/evaluations/retrieval/latest`, typed empty/completed report
  responses, and a Web Evaluation page with loading/error/empty/completed
  states and an explicit fixture-scope warning.
- Production retrieval ranking was not changed.

## Baseline

Report: `evals/retrieval/reports/latest.json`

Dataset SHA-256: `57b7ab766b2bd540037553990e92fd8fc28f1b37e70a3165acdda267f837b403`

Corpus: 4 files, 8 chunks; 14 cases

Recall@1: 0.7857; Recall@3: 1.0; Recall@5: 1.0; MRR: 0.8929

Observed query latency: P50 9.34 ms; P95 21.79 ms

This fixture is intentionally tiny and saturates by K=5. These results only
prove that the benchmark path executes and that labels resolve; they do not
baseline or satisfy production-corpus retrieval thresholds. Those remain
UNBASELINED pending a separately approved representative dataset.

## Verification

- Focused retrieval/evaluation/API/OpenAPI suite: 13 passed.
- Full Python regression suite: see final execution result for this commit.
- Web typecheck and production build passed.
- Live Web Evaluation route was inspected and showed fixture metrics and the
  non-representative-data warning.
