# Long-running Loop Progress

## Phase map

| Phase | Focus | State |
|---:|---|---|
| 0 | Baseline / architecture freeze | DONE — baseline report 000 |
| 1 | Knowledge management | NOT STARTED |
| 2 | Retrieval | NOT STARTED |
| 3 | RAG / answer quality | NOT STARTED |
| 4 | Agent / capability | NOT STARTED |
| 5 | Evaluation | NOT STARTED |
| 6 | Trace / observability | NOT STARTED |
| 7 | UI productization | NOT STARTED |
| 8 | Reliability / performance | NOT STARTED |
| 9 | Release | NOT STARTED |

## Active loop

Loop 001 is active: restore the red full-regression gate at the current
application seams. See `CURRENT_LOOP.md` and `reports/BASELINE-000.md`.

## Completed decisions incorporated into the baseline

- Router decides destination; ToolSelector/Jev chooses tools; execution policy
  authorizes execution.
- MCP readiness is domain-aware and not on the normal RAG critical path.
- Trace recording is out-of-band and must not alter SSE/chat lifecycle.
- Evidence from code examples cannot be presented as unsupported operator
  documentation.

The current baseline report determines the first feature loop. No phase is
marked complete solely because source files exist.
