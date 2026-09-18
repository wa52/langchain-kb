# Knowledge Base Architecture

The project follows Clean/Hexagonal Architecture as a modular monolith.
LangGraph, LlamaIndex, DeepSeek Harness, Chroma, BM25, and provider SDKs are
adapters; none is the business core.

## Dependency direction

```text
interfaces (Web / CLI / Feishu / MCP)
        -> application use cases
        -> ports (owned by this project)
        -> adapters (frameworks and infrastructure)
        -> external systems
```

`src/bootstrap` is the composition root. It is the only place that should
assemble concrete infrastructure into a running application.

## Stable seams

- `src/domain`: framework-free business values such as `Query`,
  `DocumentChunk`, and `RetrievalResult`.
- `src/ports`: project-owned interfaces. Application code depends on these,
  never on Chroma, LangGraph, LlamaIndex, or a provider SDK.
- `src/application`: use cases such as query, context, indexing, sessions,
  and agent orchestration.
- `src/adapters`: concrete implementations. The current Chroma/BM25 path is
  exposed through `CurrentRetrieverAdapter`; future Qdrant, LlamaIndex, or
  Elasticsearch adapters implement the same `Retriever` port.
- `src/interfaces`: transport adapters. The existing `src/api`, `src/cli`,
  `src/feishu`, and `src/mcp_stdio.py` are migrated here incrementally.
- `src/bootstrap`: composition root and lifecycle.
- `src/harness`: optional runtime utilities for event/tool/plugin composition;
  it is not the domain core and can later be replaced by DeepSeek Harness,
  LangGraph, or a project-owned Agent Runtime through `AgentRuntime`.

## Rules

1. Application code never imports a concrete framework or storage adapter.
2. A port has project-owned types and error semantics; adapters translate to
   and from framework-specific types at the seam.
3. `AgentRuntime` is an adapter behind the application interface. The KB does
   not become “a LangGraph project” or “a DeepSeek Harness project”.
4. Web, CLI, Feishu, and MCP call the same use cases and do not duplicate
   session, retrieval, tool, or persistence logic.
5. `bootstrap` is the only composition root. Global constructors are legacy
   compatibility seams and should not be added to new code.

## Migration order

1. Domain values and ports.
2. Retrieval and reranking adapters.
3. Query/context application services.
4. Agent Runtime adapter (current LangGraph implementation first).
5. Session/event persistence adapters.
6. Remove legacy compatibility implementations after downstream callers have
   migrated.

The first vertical slice is now present: the `/retrieval/search` endpoint calls
`QueryService`, which depends on the project-owned `Retriever` port; the
existing Chroma/BM25 implementation is wrapped by `CurrentRetrieverAdapter`.
The current LangGraph implementation is also wrapped by
`LangGraphAgentRuntime`, which implements the project-owned `AgentRuntime`
seam.

The Web routers for chat, search, indexing, files, and sessions now enter
through application facades. MCP uses the same facades. The old API service
modules remain only as compatibility implementations while their internals are
being moved behind the new ports.
