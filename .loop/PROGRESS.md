# Long-running Loop Progress

## Phase map

| Phase | Focus | State |
|---:|---|---|
| 0 | Baseline / architecture freeze | DONE — baseline report 000 |
| 1 | Knowledge management | NOT STARTED |
| 2 | Retrieval | IN PROGRESS — debugger and isolated quality evaluation delivered; production target unbaselined |
| 3 | RAG / answer quality | NOT STARTED |
| 4 | Agent / capability | NOT STARTED |
| 5 | Evaluation | IN PROGRESS — routing and isolated retrieval evaluations exist; answer/tool evaluations remain |
| 6 | Trace / observability | NOT STARTED |
| 7 | UI productization | NOT STARTED |
| 8 | Reliability / performance | NOT STARTED |
| 9 | Release | NOT STARTED |

## Active loop

Loop 001 is DONE: 727 passed, 1 skipped. Loop 002 is DONE: retrieval debugger
API/UI delivered; 730 passed, 1 skipped after the final added empty-results
case; production build and live retrieval UI passed. Loop 003 is DONE:
isolated retrieval evaluation runner/report and Web viewer delivered; see
`reports/LOOP-003.md`. No actual personal corpus was read or changed.

Loop 004 is active: Web Capability Catalog gap analysis and user-facing
discovery/status view. See `CURRENT_LOOP.md` for its acceptance gate.

## Completed decisions incorporated into the baseline

- Router decides destination; ToolSelector/Jev chooses tools; execution policy
  authorizes execution.
- MCP readiness is domain-aware and not on the normal RAG critical path.
- Trace recording is out-of-band and must not alter SSE/chat lifecycle.
- Evidence from code examples cannot be presented as unsupported operator
  documentation.

The current baseline report determines the first feature loop. No phase is
marked complete solely because source files exist.
