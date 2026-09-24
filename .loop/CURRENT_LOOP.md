# Loop 003 — Retrieval Quality Evaluation Runner

## Prior loop result

Loop 001 aligned legacy tests with the current application seams and restored
the full regression gate. Loop 002 delivered the Retrieval Debugger UI and
passed live Web verification plus the full test suite. See `reports/LOOP-001.md`
and `reports/LOOP-002.md`.

## Acceptance

- [ ] Define a versioned, repository-safe retrieval case format with query and
      expected source/chunk identifiers; do not use private corpus data.
- [ ] Implement a deterministic runner over the existing retrieval seam and
      report Recall@K, MRR, and per-case hit/rank evidence.
- [ ] Add a labeled case set with coverage across Chinese natural language,
      operator names, code examples, and paraphrases.
- [ ] Record reproducible baseline results and timing; do not claim numeric
      targets until they are demonstrated.
- [ ] Add tests for metrics, malformed cases, empty results, and report output.
- [ ] Provide a user-facing Web/API entry to run or inspect an evaluation, with
      loading, empty, error, and completed states.
- [ ] Preserve Fast RAG behaviour; no production ranking changes in this loop.

## Scope guard

Do not alter Fast RAG ranking or tune production behavior to fit evaluation
cases. The runner must consume the project-owned retrieval seam, use synthetic
or explicitly shareable fixtures, and report failures instead of rewriting
gold labels.
