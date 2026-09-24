# Knowledge Agent Platform: Product Goal

## Outcome

Build a long-running, maintainable, extensible, and measurable Knowledge Agent
Platform. Users can import and maintain personal or project knowledge, ask
grounded questions in natural language, and let an agent use knowledge and
external capabilities under explicit execution controls.

## Product scope

- **Knowledge** — sources, parsing, chunking, metadata, indexing, versioning,
  and health.
- **Retrieval** — dense, BM25, hybrid fusion, reranking, filtering, and a
  debugger.
- **AI** — direct answers, fast RAG, agent mode, citations, and evidence
  boundaries.
- **Agent** — capability catalog, MCP, tool selection (including optional
  Jev), execution policy, approval, and recoverable tool execution.
- **Quality** — routing/retrieval/answer/tool evaluations, performance data,
  and execution traces.
- **Interfaces** — Web, REST API, MCP server, CLI, and Feishu.

## Non-goals

- A coding or test agent.
- A mail client, full browser agent, ERP, or MES.
- Re-implementing external capabilities inside the knowledge base. Those stay
  external capabilities behind the catalog/MCP seam.

## Completion authority

No implementation task may declare the project complete. Completion requires
the acceptance matrix to pass, a release regression report, and explicit human
acceptance.
