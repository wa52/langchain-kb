# Long-running Loop Progress

## Phase map

| Phase | Focus | State |
|---:|---|---|
| 0 | Baseline / architecture freeze | DONE — baseline report 000 |
| 1 | Knowledge management | IN PROGRESS — explicit source health audit delivered; source add/remove/refresh lifecycle remains |
| 2 | Retrieval | IN PROGRESS — debugger and isolated quality evaluation delivered; production target unbaselined |
| 3 | RAG / answer quality | IN PROGRESS — HALCON evidence and example-only abstention Harbor cases pass; representative answer benchmark remains |
| 4 | Agent / capability | IN PROGRESS — scoped filesystem tools delivered; real tool-selection evaluation and policy acceptance remain |
| 5 | Evaluation | IN PROGRESS — routing, retrieval, and two focused answer-grounding evaluations exist; representative answer/tool quality baselines remain |
| 6 | Trace / observability | IN PROGRESS — run_id viewer delivered; persistent trace history/replay remains out of scope |
| 7 | UI productization | IN PROGRESS — Retrieval, Evaluation, Capability, Trace, and source health pages delivered; richer answer UX remains |
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

Loop 009 is DONE: short access-failure follow-ups inherit only the immediately
preceding explicit filesystem task and route back to Agent with read-only
filesystem intent. Focused tests passed (39); full suite passed (775 passed,
1 skipped). No user file contents were read or hashed. See `reports/LOOP-009.md`.

Loop 010 is DONE: an explicitly triggered, asynchronous source health audit
classifies every tracked entry across internal, external, and experience roots
as healthy, missing, changed, duplicate, unreadable, or unresolved. It hashes
only tracked files under configured roots, blocks traversal/symlink escapes,
and returns no content, digest, or absolute path. The Knowledge page exposes
progress and results without scanning on page load. Focused tests: 12 passed,
1 skipped; full suite: 783 passed, 2 skipped; web typecheck and production
build passed. The live service served the built page and exposes the new routes.
The real user corpus was not scanned and the UI action was not triggered;
synthetic API/service tests cover that flow. See `reports/LOOP-010.md`.

Loop 011 is DONE: a second real Harbor task runs the production `FastRagService`
with only a synthetic HDevelop example and tests abstention from undocumented
operator/parameter claims. The independent semantic judge was calibrated on a
valid abstention and a plausible fabricated answer (both expected decisions
passed); the Harbor run completed 1/1 with reward 1.0 and zero errors. The
answer used one LLM call (12.03 s). The full suite passed (786 passed, 1
skipped); no personal corpus/history/MCP was accessed. This is a targeted
regression case, not a representative answer-quality baseline; citation and
unsupported-claim thresholds remain UNBASELINED. See `reports/LOOP-011.md` and
`evals/jobs/loop011-halcon-example-only/`.

Loop 012 is DONE: Jev uses the endpoint matching its key provider. A `vck_`
Gateway key previously received HTTP 401 from TypeSafe's direct host; the
official Vercel-compatible endpoint now receives HTTP 403. Settings offers an
explicit synthetic connection check and labels a saved key as configured,
not verified. Agent selection falls back to rules and skips repeated network
calls after an authorization rejection until the key changes; the check can
reprobe. Focused API, selector, and OpenAPI tests passed (43), and the full
regression passed (793 passed, 1 skipped). Web typecheck/build passed; the
running page displayed the Gateway 403 state. A Feishu test that used to write
the repo-root `no_such.json` now uses a per-test temporary store.
The real Jev comparison is blocked by the Gateway account's 403 response and
its quality metrics remain unbaselined. See `reports/LOOP-012.md`.

## Completed decisions incorporated into the baseline

- Router decides destination; ToolSelector/Jev chooses tools; execution policy
  authorizes execution.
- MCP readiness is domain-aware and not on the normal RAG critical path.
- Trace recording is out-of-band and must not alter SSE/chat lifecycle.
- Evidence from code examples cannot be presented as unsupported operator
  documentation.

The current baseline report determines the first feature loop. No phase is
marked complete solely because source files exist.
