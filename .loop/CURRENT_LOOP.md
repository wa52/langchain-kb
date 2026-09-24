# Loop 005 — Completed-Run Trace Viewer

## Prior loop result

Loop 004 delivered a read-only Capability Catalog and verified that page
refreshes do not start MCP discovery. See `reports/LOOP-004.md`.

## Goal

Give users a dedicated Web surface to inspect one completed Agent run by its
`run_id`, using the existing out-of-band trace query. Do not change the chat or
SSE execution lifecycle.

## Acceptance

- [ ] Add a Traces Web navigation entry and dedicated run lookup page.
- [ ] Use only the existing completed-trace query; do not introduce a trace
      list endpoint or change trace storage/lifecycle.
- [ ] Present the ordered action chain (selector, each model invocation,
      tool calls/results, verification, completion) with true payload durations
      where available; never display hidden chain-of-thought.
- [ ] Safely format JSON/text payloads as inert text; avoid HTML interpretation
      and handle long arguments/results without breaking the layout.
- [ ] Include loading, not-found/empty, error/retry, and completed states.
- [ ] Add API/client contract coverage and verify unknown and synthetic
      completed run IDs without reading previous user conversations.
- [ ] Verify Web desktop and narrow layout, typecheck/build, and no changes to
      SSE, ConversationService, AgentRuntime, or trace lifecycle.

## Scope guard

Do not automatically enumerate historical runs, read personal trace contents,
or change any chat execution behavior. Verification uses a synthetic trace
fixture and an intentionally unknown run ID only.
