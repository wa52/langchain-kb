# Long-running Loop Progress

## Phase map

| Phase | Focus | State |
|---:|---|---|
| 0 | Baseline / architecture freeze | DONE — baseline report 000 |
| 1 | Knowledge management | NOT STARTED |
| 2 | Retrieval | IN PROGRESS — debugger and isolated quality evaluation delivered; production target unbaselined |
| 3 | RAG / answer quality | NOT STARTED |
| 4 | Agent / capability | IN PROGRESS — read-only runtime catalog delivered; tool-selection eval and policy acceptance remain |
| 5 | Evaluation | IN PROGRESS — routing and isolated retrieval evaluations exist; answer/tool evaluations remain |
| 6 | Trace / observability | IN PROGRESS — run_id viewer delivered; persistent trace history/replay remains out of scope |
| 7 | UI productization | IN PROGRESS — Retrieval, Evaluation, Capability, and Trace pages delivered; source health and richer answer UX remain |
| 8 | Reliability / performance | NOT STARTED |
| 9 | Release | NOT STARTED |

## Active loop

Loop 001 is DONE: 727 passed, 1 skipped. Loop 002 is DONE: retrieval debugger
API/UI delivered; 730 passed, 1 skipped after the final added empty-results
case; production build and live retrieval UI passed. Loop 003 is DONE:
isolated retrieval evaluation runner/report and Web viewer delivered; see
`reports/LOOP-003.md`. No actual personal corpus was read or changed.

Loop 004 is DONE: read-only Capability Catalog API and responsive Web page;
744 passed, 1 skipped; web typecheck/build and live page verified. Viewing the
page did not trigger MCP discovery. See `reports/LOOP-004.md`.

Loop 005 is DONE: completed-run Trace Viewer; 746 passed, 1 skipped; Web
typecheck/build passed; desktop and 390px iframe layout plus synthetic
completed/not-found states verified. Secret and hidden-reasoning fields were
checked against synthetic data only. See `reports/LOOP-005.md`.

Loop 006 is DONE: synthetic offline Rule baseline and deterministic Jev adapter
simulation, report API, and Evaluation Web comparison delivered. Full suite:
760 passed, 1 skipped. The Jev simulation must not be interpreted as real Jev
quality; no external call or user data was used. See `reports/LOOP-006.md`.

Loop 007 is DONE: Harbor 0.23.0 Docker task exercises the production
`FastRagService` with a synthetic HALCON `lines_facet` example and frozen,
paraphrased HALCON 24.11.3.0 operator-reference facts. Semantic verifier
calibration passed both a correct paraphrase and a plausible wrong answer; the
real one-attempt Harbor run completed 1/1 with reward 1.0 and no trial errors.
Full project suite passed in `kb_env`: 760 passed, 1 skipped, 3 warnings. The
measured RAG stages were
search 0 ms, gate 0.09 ms, context 0.1 ms, one LLM call 8760.03 ms. The adapter
and verifier call the API in host subprocesses, so the Docker no-network policy
applies to the task container only; only synthetic prompt/evidence text was
sent. No production corpus, history, or MCP was accessed. See
`reports/LOOP-007.md`, `evals/jobs/loop007-halcon-fast-rag-evidence/`, and
`evals/harbor_agents/calibration.json`.

Loop 008 is DONE: filesystem actions route to Agent; bounded inspect and
approval-gated indexing tools are implemented with configured-root checks,
cross-source hash deduplication, Capability API exposure, and synthetic tests.
Full suite: 773 passed, 1 skipped. No real user directory was scanned. See
`reports/LOOP-008.md`.

## Completed decisions incorporated into the baseline

- Router decides destination; ToolSelector/Jev chooses tools; execution policy
  authorizes execution.
- MCP readiness is domain-aware and not on the normal RAG critical path.
- Trace recording is out-of-band and must not alter SSE/chat lifecycle.
- Evidence from code examples cannot be presented as unsupported operator
  documentation.

The current baseline report determines the first feature loop. No phase is
marked complete solely because source files exist.
