# Baseline Report 000

**Recorded:** 2026-09-24  
**Scope:** inventory and verification only; no production chat, RAG, SSE, or
Feishu behaviour was changed.

## Inventory result

- Python suite: **727 tests collected**.
- Web client: `npm run typecheck` and `npm run build` both passed.
- Existing product coverage includes hybrid retrieval, routing evaluation,
  MCP/ToolRegistry, agent traces, API/CLI/MCP, Web serving, lifecycle, and
  Feishu bridge behaviour.

## Python regression result

The repository's global Python cannot serve as this project's test environment:
it has MCP 2.x for another installed project, while this repository declares
MCP 1.x. The global package was restored after verification. The final baseline
was run in the project `kb_env` with a project-local pytest temporary directory.

```text
709 passed, 18 failed, 1 skipped, 3 warnings in 135.37s
```

### Failure clusters

| Cluster | Failures | Finding |
|---|---:|---|
| Legacy agent-chat mocks | 5 | Tests patch the former `api.services.chat` execution path, but generic inputs now correctly route through Direct/Fast RAG. |
| Legacy SSE mocks | 8 | Stream tests send `hi`, which is deliberately a fixed, no-LLM greeting path; they therefore never reach mocked Agent streaming. |
| Legacy CLI chat mocks | 5 | CLI now uses the application conversation seam; tests still patch the removed API-service seam. |

This is not evidence to remove the current fast greeting/router behaviour.
The first active implementation loop must move the regression tests to the
current application seam and use explicit Agent-route inputs for Agent/SSE
contract tests.

## Other baseline findings

- `requests` reports an optional character-detection dependency warning in
  `kb_env`; it is non-failing and should be tracked during dependency hygiene.
- LangChain/Pydantic deprecation warnings are non-failing and must not be
  hidden; they are not the selected highest-priority gap.

## Selected next loop

**Loop 001 — Chat execution regression contract alignment.** It has the
highest priority because a full regression gate is red. Its goal is to retain
the user-visible direct/greeting optimisation while restoring tests at the
current ConversationService/AgentRuntime seams. No production routing or SSE
lifecycle changes are authorised by this loop.
