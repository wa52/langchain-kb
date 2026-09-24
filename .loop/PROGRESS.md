# Long-running Loop Progress

## Phase map

| Phase | Focus | State |
|---:|---|---|
| 0 | Baseline / architecture freeze | DONE — baseline report 000 |
| 1 | Knowledge management | NOT STARTED |
| 2 | Retrieval | IN PROGRESS — debugger UI delivered; quality evaluation next |
| 3 | RAG / answer quality | NOT STARTED |
| 4 | Agent / capability | NOT STARTED |
| 5 | Evaluation | IN PROGRESS — retrieval benchmark is next |
| 6 | Trace / observability | NOT STARTED |
| 7 | UI productization | NOT STARTED |
| 8 | Reliability / performance | NOT STARTED |
| 9 | Release | NOT STARTED |

## Active loop

Loop 001 is DONE: 727 passed, 1 skipped. Loop 002 is DONE: retrieval debugger
API/UI delivered; 730 passed, 1 skipped after the final added empty-results
case; production build and live retrieval UI passed. Loop 003 is active:
reproducible retrieval quality evaluation. See `CURRENT_LOOP.md` and reports.

## Completed decisions incorporated into the baseline

- Router decides destination; ToolSelector/Jev chooses tools; execution policy
  authorizes execution.
- MCP readiness is domain-aware and not on the normal RAG critical path.
- Trace recording is out-of-band and must not alter SSE/chat lifecycle.
- Evidence from code examples cannot be presented as unsupported operator
  documentation.

The current baseline report determines the first feature loop. No phase is
marked complete solely because source files exist.
