# Loop 002 — Retrieval Debugger UI

## Prior loop result

Loop 001 aligned legacy tests with the current application seams and restored
the full regression gate. See `reports/LOOP-001.md`.

## Acceptance

- [ ] A Web navigation entry opens the Retrieval page.
- [ ] A user can submit a query and see ordered Top-K results.
- [ ] Each result exposes source, chunk/excerpt, Dense, BM25, fusion/final
      score, rank, and elapsed time where available.
- [ ] Loading, empty, error, long Chinese text, and code-content states are
      covered.
- [ ] API and Web tests pass; existing Fast RAG behaviour is unchanged.

## Scope guard

Do not duplicate hybrid retrieval in the UI. The page must consume the
project-owned retrieval/API seam; it must not change Fast RAG scoring, agent
selection, or Feishu delivery.
