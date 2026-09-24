# Loop 006 — Tool Selection Evaluation Runner

## Prior loop result

Loop 005 delivered a run_id Trace Viewer with synthetic completed/not-found
verification, secret/reasoning redaction, and responsive desktop/narrow layouts.
It made no SSE or chat execution lifecycle changes. See `reports/LOOP-005.md`.

## Goal

Measure whether the current ToolSelector (and optional Jev selector) ranks
relevant tools well on a frozen, repository-safe synthetic test set. Report
tradeoffs such as Top-1/Top-3 recall, write-tool exposure, and latency instead
of claiming that Jev is effective merely because an API call succeeds.

## Acceptance

- [x] Add a versioned, repository-owned tool-selection case set with expected
      tool IDs and independent coverage across knowledge, graph, workflow,
      external read, and external write intents.
- [x] Add deterministic RuleBased evaluation using the real selector seam;
      report Top-1, Top-3 recall, per-case ranks, write-tool false exposure,
      and latency without modifying production selection.
- [x] Add an offline Jev simulation mode using the existing adapter seam; do
      not require or read configured credentials.
- [x] Keep simulated Jev outcomes separate from Rule baseline, record provider
      mode and dataset hash, and never label simulation as a real Jev result.
- [x] Add tests for metrics, bad cases, no-key behavior, adapter failures, and
      report redaction/output.
- [x] Show baseline/simulation result availability in the Evaluation Web page, with
      loading/empty/error/completed states; never silently treat Jev as run.
- [x] Preserve selector and Agent behavior. No external Jev call is in scope.

## Scope guard

Do not read live MCP configuration, user prompts, chat history, or the personal
knowledge corpus. Use synthetic ToolSpecs and cases. Do not tune selector
rules/golden labels to force passing scores; this loop measures only.

## Boundary and result

The approved scope is offline-only: repository-owned synthetic queries and
ToolSpecs, real RuleBased selector, and a deterministic request stub injected
through the Jev adapter. It never reads `TYPESAFE_API_KEY` or sends requests to
TypeSafe. The Jev result is an adapter-flow simulation, not evidence of real Jev
quality. See `reports/LOOP-006.md` and `evals/tools/reports/latest.json`.
