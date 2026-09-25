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

## ADR-0006 — Retrieval benchmark uses a frozen, isolated fixture corpus

**Decision:** Keep the checked-in retrieval dataset limited to hash-pinned
repository-owned examples. The runner builds an isolated temporary index with
offline embeddings and no LLM or external service credentials.

**Reason:** Benchmarking must be reproducible and must not scan or modify the
user's personal knowledge corpus. The current small fixture validates the
measurement pipeline only; its scores must not be represented as production
quality evidence.

## ADR-0007 — Capability catalog reads state but never initializes tools

**Decision:** The Capability Catalog projects existing registry metadata and
MCP readiness only. Page loads and refreshes do not start discovery, connect to
servers, or execute tools.

**Reason:** MCP is an optional capability and must remain off the normal
startup and browsing critical path.

## ADR-0008 — Trace inspection is opt-in by run_id

**Decision:** The Trace UI queries only a user-entered run_id and does not list
or automatically load previous runs. Rendering omits hidden-reasoning fields
and masks credential-like keys.

**Reason:** Users can inspect a specific run without exposing unrelated chat
history or turning observability into a new chat execution dependency.

## ADR-0009 — Local filesystem capability is allowlist-scoped and content-minimal

**Decision:** Native filesystem tools may only access existing paths under the
enabled filesystem MCP command's configured roots. Inspection returns supported
file names/counts and SHA-256 duplicate matches, never document bodies. Imports
go through the existing ingestion service, compare hashes against all tracked
sources, and require Agent approval.

**Reason:** Configuring an MCP server does not mean every local path should be
implicitly available to the Agent. The capability must be useful without
granting unrestricted disk access or duplicating already indexed knowledge.
