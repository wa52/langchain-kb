# Decision Log

## ADR-0001 — Preserve the existing architecture seams

**Decision:** Use the established Decision Layer → ToolSelector/Jev →
AgentRuntime → ToolRegistry/ExecutionPolicy chain. Do not re-open a general
architecture refactor during product loops.

**Reason:** The current seams allow independent routing, capability selection,
and authorization. Product gaps are now more valuable than directory churn.

## ADR-0002 — Trace is observational, not a chat dependency

**Decision:** Record completed Agent runs out of band and query by `run_id`.

**Rule:** Do not make SSE or conversation completion depend on trace writes.

## ADR-0003 — Fast RAG excludes per-document LLM grading

**Decision:** Preserve fast-path retrieval without auxiliary per-document LLM
grading.

**Reason:** It adds tail latency and conflicts with the fast RAG target.

## ADR-0004 — UI is part of a product capability

**Decision:** A user-facing capability is only done with backend, API, UI,
tests, and applicable evaluation evidence.

## ADR-0005 — MCP metadata is verified at its lifecycle seam

**Decision:** Verify MCP metadata at `_register_mcp_entries`, and separately
verify that agent creation starts asynchronous discovery.

**Reason:** MCP catalog discovery is intentionally asynchronous. Testing an
agent constructor as if it synchronously loaded all MCP servers contradicts
the readiness/lifecycle design and produces a false regression.
