# Requirement Matrix

Status values: `DONE`, `PARTIAL`, `MISSING`, `BLOCKED`. `DONE` means there is
an implemented user-facing path and automated coverage; it does not by itself
mean the product has been release-accepted.

| Area | Requirement | Status | Existing evidence / next evidence |
|---|---|---:|---|
| Knowledge | Source indexing and file lifecycle | PARTIAL | Index, file, sync routers and Knowledge page exist; source version/health UI is missing. |
| Knowledge | Parsing, chunks, metadata | DONE | Ingestion/vector-store tests and API paths exist. |
| Knowledge | Source health, duplicates, staleness | MISSING | No dedicated product API/page or acceptance eval. |
| Retrieval | Dense + BM25 hybrid retrieval | DONE | `src/retrieval`, hybrid behavior tests. |
| Retrieval | Cache and latency telemetry | DONE | Retrieval cache and telemetry tests. |
| Retrieval | Retrieval debugger in Web | DONE | `POST /api/v1/retrieval/debug`, dedicated responsive page, backend contract tests, production build, live Web query verified. |
| AI | Direct, Fast RAG, Agent routing | DONE | Routing service and 100-case routing evaluation. |
| AI | Citations and evidence boundary | PARTIAL | Citation/evidence code exists; grounded-answer benchmark is not yet established. |
| Agent | Capability catalog + native tools | DONE | Harness/ToolRegistry and agent tests. |
| Agent | MCP lifecycle/readiness | DONE | Domain-aware readiness implementation and tests. |
| Agent | Tool selection / optional Jev | PARTIAL | Selector exists; comparative tool-selection evaluation is missing. |
| Agent | Policy, approval, retry | PARTIAL | Approval/recovery exists; policy acceptance coverage is incomplete. |
| Quality | Routing evaluation | DONE | 100 labeled cases, macro-F1 gate. |
| Quality | Retrieval, answer, and tool evaluations | PARTIAL | Routing eval and isolated retrieval fixture runner/report exist; answer/tool evals remain missing and real retrieval target remains unbaselined. |
| Quality | Agent trace and timing | PARTIAL | Completed trace API and developer pane exist; dedicated Trace page/replay is missing. |
| Interfaces | Web chat, sources/settings/status | DONE | React pages and API clients exist. |
| Interfaces | Retrieval/Capabilities/Evaluation/Traces UI | PARTIAL | Retrieval debugger, Evaluation, and read-only Capability Catalog pages exist; dedicated Traces viewer remains missing. |
| Interfaces | REST API, CLI, MCP | DONE | FastAPI routers, CLI, and MCP endpoint exist. |
| Interfaces | Feishu | PARTIAL | Bridge works; real-delivery performance/reliability acceptance is pending. |
| Reliability | Lifecycle, reload, port recovery | PARTIAL | Managed `knowledge web` lifecycle exists; endurance and shutdown acceptance is missing. |
| Release | Security, documentation, deployment, release gate | MISSING | No release checklist/report yet. |

## Prioritisation rule

Choose the highest-impact `MISSING` or `PARTIAL` gap whose acceptance can be
measured without weakening existing gates. Do not add a second capability while
the current loop's acceptance is failing.
