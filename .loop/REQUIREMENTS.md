# Requirement Matrix

Status values: `DONE`, `PARTIAL`, `MISSING`, `BLOCKED`. `DONE` means there is
an implemented user-facing path and automated coverage; it does not by itself
mean the product has been release-accepted.

| Area | Requirement | Status | Existing evidence / next evidence |
|---|---|---:|---|
| Knowledge | Source indexing and file lifecycle | PARTIAL | Index, file, sync routers and Knowledge page exist; source version/health UI is missing. |
| Knowledge | Parsing, chunks, metadata | DONE | Ingestion/vector-store tests and API paths exist. |
| Knowledge | Source health, duplicates, staleness | DONE | Loop 010 added an explicit source audit API and Knowledge-page results, with synthetic coverage and no scan on page load. |
| Retrieval | Dense + BM25 hybrid retrieval | DONE | `src/retrieval`, hybrid behavior tests. |
| Retrieval | Cache and latency telemetry | DONE | Retrieval cache and telemetry tests. |
| Retrieval | Retrieval debugger in Web | DONE | `POST /api/v1/retrieval/debug`, dedicated responsive page, backend contract tests, production build, live Web query verified. |
| AI | Direct, Fast RAG, Agent routing | DONE | Routing service and 100-case routing evaluation. |
| AI | Citations and evidence boundary | PARTIAL | Fast RAG evidence constraints exist; Loop 007 validates one HALCON example/reference case with a semantic judge. A broader grounded-answer benchmark remains. |
| Agent | Capability catalog + native tools | DONE | Harness/ToolRegistry, scoped local filesystem inspection/index tools, capability API tests. |
| Agent | Authorized local-folder inspection and indexing | DONE | Filesystem root allowlist, hash-only duplicate inspection, approval-gated existing ingestion path, cross-source dedupe regression. |
| Agent | MCP lifecycle/readiness | DONE | Domain-aware readiness implementation and tests. |
| Agent | Tool selection / optional Jev | PARTIAL | Selector and isolated Rule-vs-Jev-adapter simulation exist. Loop 012 routes Vercel keys to the compatible Gateway API and exposes an explicit connection check; the configured Gateway account returns 403, so real Jev quality remains unmeasured. |
| Agent | Policy, approval, retry | PARTIAL | Approval/recovery exists; policy acceptance coverage is incomplete. |
| Quality | Routing evaluation | DONE | 100 labeled cases, macro-F1 gate. |
| Quality | Retrieval, answer, and tool evaluations | PARTIAL | Routing, isolated retrieval, and synthetic tool-selection runner/report exist. Loop 007 adds one Harbor Fast RAG evidence-boundary case; broad answer evaluation, real Jev comparison, and production retrieval target remain unbaselined. |
| Quality | Agent trace and timing | DONE | Out-of-band completed-run query, per-run Trace Viewer, exact action durations, and secret/reasoning-safe display. Trace persistence/replay across process restarts remains out of scope. |
| Interfaces | Web chat, sources/settings/status | DONE | React pages and API clients exist. |
| Interfaces | Retrieval/Capabilities/Evaluation/Traces UI | DONE | Retrieval debugger, Evaluation (including synthetic tool-selection comparison), read-only Capability Catalog, and run_id Trace Viewer pages are present. |
| Interfaces | REST API, CLI, MCP | DONE | FastAPI routers, CLI, and MCP endpoint exist. |
| Interfaces | Feishu | PARTIAL | Bridge works; real-delivery performance/reliability acceptance is pending. |
| Reliability | Lifecycle, reload, port recovery | PARTIAL | Managed `knowledge web` lifecycle exists; endurance and shutdown acceptance is missing. |
| Release | Security, documentation, deployment, release gate | MISSING | No release checklist/report yet. |

## Prioritisation rule

Choose the highest-impact `MISSING` or `PARTIAL` gap whose acceptance can be
measured without weakening existing gates. Do not add a second capability while
the current loop's acceptance is failing.
