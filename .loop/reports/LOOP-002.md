# Loop 002 — Retrieval Debugger UI

## Outcome

Delivered a separate Retrieval Debugger page and API route. The UI calls the
application's existing scored-retrieval seam; it does not implement its own
ranking or invoke the answer-generation path.

## Evidence

- `POST /api/v1/retrieval/debug` returns ordered candidates with source,
  chunk ID, excerpt, Dense/BM25/fusion scores and channel/final ranks.
- The Web page provides query and Top-K controls, loading/error/empty/completed
  states, retry, responsive layout, and readable long code/Chinese excerpts.
- Live browser verification ran `HALCON lines_facet 算子`, returned five ranked
  results, and showed a total retrieval duration of 281.8 ms. Results included
  a Chinese index excerpt and a `.hdev` code example.
- `npm run typecheck`: PASS.
- `npm run build`: PASS.
- Retrieval debugger/OpenAPI focused tests: PASS (3 debugger cases plus exact
  OpenAPI operation IDs).
- Full suite: `730 passed, 1 skipped, 3 warnings` in 56.52s, clean exit code.
- `git diff --check`: PASS.

## Limitations

- The endpoint duration is total retrieval time; individual candidate-level
  duration is not meaningful/available from the current retrieval contract.
- Error and empty UI branches are present. Empty API behavior has a regression
  test; the app currently has no dedicated React component test harness.
- The existing retrieval application helper still owns concrete retrieval
  details. This loop intentionally reuses it; dependency-direction cleanup is
  tracked as a separate architecture-quality gap, not expanded here.

## Decision

No production retrieval/ranking changes were made. Continue with a stable,
shareable retrieval evaluation dataset and runner in Loop 003.
