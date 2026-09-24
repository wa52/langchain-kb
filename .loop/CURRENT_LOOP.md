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

- [ ] Add a versioned, repository-owned tool-selection case set with expected
      tool IDs and independent coverage across knowledge, graph, workflow,
      external read, and external write intents.
- [ ] Add deterministic RuleBased evaluation using the real selector seam;
      report Top-1, Top-3 recall, per-case ranks, write-tool false exposure,
      and latency without modifying production selection.
- [ ] Add an optional Jev evaluation mode using the existing adapter; require
      configured credentials explicitly and never print/store the key.
- [ ] Keep Jev outcomes separate from Rule baseline, record provider mode,
      dataset hash, errors/fallbacks, and mark network-dependent results clearly.
- [ ] Add tests for metrics, bad cases, no-key behavior, adapter failures, and
      report redaction/output.
- [ ] Show both baseline/result availability in the Evaluation Web page, with
      loading/empty/error/completed states; never silently treat Jev as run.
- [ ] Preserve selector and Agent behavior. Run the real external Jev suite
      only on this synthetic dataset and keep its outcome labeled as such.

## Scope guard

Do not read live MCP configuration, user prompts, chat history, or the personal
knowledge corpus. Use synthetic ToolSpecs and cases. Do not tune selector
rules/golden labels to force passing scores; this loop measures only.
