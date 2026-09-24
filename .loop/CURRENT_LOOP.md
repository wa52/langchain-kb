# Loop 003 — Retrieval Quality Evaluation Runner (completed)

## Prior loop result

Loop 001 aligned legacy tests with the current application seams and restored
the full regression gate. Loop 002 delivered the Retrieval Debugger UI and
passed live Web verification plus the full test suite. See `reports/LOOP-001.md`
and `reports/LOOP-002.md`.

## Acceptance — PASS

- [x] Define a versioned, repository-safe retrieval case format with query and
      expected source/chunk identifiers; do not use private corpus data.
- [x] Implement a deterministic runner over the existing retrieval seam and
      report Recall@K, MRR, and per-case hit/rank evidence.
- [x] Add a labeled case set with coverage across Chinese natural language,
      operator names, code examples, and paraphrases.
- [x] Record reproducible baseline results and timing; do not claim numeric
      targets until they are demonstrated.
- [x] Add tests for metrics, malformed cases, empty results, and report output.
- [x] Provide a user-facing Web/API entry to run or inspect an evaluation, with
      loading, empty, error, and completed states.
- [x] Preserve Fast RAG behaviour; no production ranking changes in this loop.

## Result

The isolated fixture report is `evals/retrieval/reports/latest.json` and is
available in Web under Evaluation. It uses 14 queries over 4 hash-pinned,
repository-owned documents (8 chunks): Recall@1 0.7857, Recall@3/5 1.0, MRR
0.8929, P50 9.34 ms, P95 21.79 ms. These numbers validate the harness and
fixture only; they do not satisfy or baseline production-corpus targets. The
Retrieval product targets remain UNBASELINED pending an explicitly approved,
representative dataset.

Verification: focused suite 13 passed; full suite, web typecheck/build, and
live Web inspection are recorded in `reports/LOOP-003.md`.

## Scope guard

Do not alter Fast RAG ranking or tune production behavior to fit evaluation
cases. The runner must consume the project-owned retrieval seam, use synthetic
or explicitly shareable fixtures, and report failures instead of rewriting
gold labels.
