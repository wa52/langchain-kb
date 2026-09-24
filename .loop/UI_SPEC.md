# Product UI Contract

The Web client is a product interface, not an optional presentation layer. A
deliverable is incomplete until its supported workflow is reachable and
verifiable in the UI.

## Target navigation

`Chat`, `Knowledge`, `Retrieval`, `Capabilities`, `Evaluation`, `Traces`,
`Status`, `Settings`.

## Required user-visible behaviour

- **Chat:** streaming answer, citations/sources, session history, agent state,
  and approval.
- **Knowledge:** source list, add/sync/remove, chunk count, type/status, and
  health summary.
- **Retrieval:** query test surface, ranked chunks, dense/BM25/fusion scores,
  source metadata, latency, loading/empty/error states.
- **Capabilities:** native/MCP capability list, readiness, enabled state, and
  risk/read-write status.
- **Evaluation:** latest metrics, dataset/run identity, and an explicit run
  action with failure state.
- **Traces:** completed run lookup/replay; route, MCP readiness, tool
  selection, model calls, tool calls, errors, and real durations.
- **Status/Settings:** health and configurable providers/keys without exposing
  secrets.

Every new page must cover loading, empty, error, success, Chinese text, long
text, and code/citation content where applicable.
