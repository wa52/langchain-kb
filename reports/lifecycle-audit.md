# Lifecycle Audit

## 1. Document Parsing, Splitting, and Vectorization Entry Points

**Current state:** Three distinct entry paths, all in `pipeline.py`:

| Entry | Trigger | Full pipeline | Incremental |
|-------|---------|---------------|-------------|
| `run_ingestion()` | `/ingest`, `cli ingest`, `cli rebuild` | load → split → embed → store → BM25 → graph | No (trashes everything) |
| `run_add_path()` | `/add <path>`, `cli add` | copy → load → split → embed → store → BM25 → graph | No (always full re-index of added file) |
| `run_incremental_update()` | `cli update` | diff tracker → delete → reload → split → embed → store → BM25 → graph | Yes |
| `run_single_file_update()` | `cli update-file` | delete → load → split → embed → store → BM25 → graph | Yes (single file) |

**Problem:** Three out of four paths smear the same 6 steps across `pipeline.py`. Steps are not composable — you cannot say "re-embed only" or "rebuild BM25 only" without calling specific functions.

## 2. Embedding Model Initialization

**File:** `src/vector_store/embedding.py:13` — `get_embedding_model()`, `@lru_cache(maxsize=1)`.

Called from:
- `rag_agent.py:28` (agent load, main thread, with `HF_HUB_DISABLE_PROGRESS_BARS=1`)
- `pipeline.py:27` (ingestion — no progress bar suppression)
- `commands.py:61` (rebuild command, no progress bar suppression)
- `chroma_client.py:16` (lazy init when `get_vector_store()` is called with no embeddings arg)
- `retriever.py:21` (every `get_retriever()` call — because Chroma retriever needs embeddings)

**Problem:** Since `get_vector_store()` without args falls back to `get_embedding_model()`, and `get_retriever()` calls both, every single chat query triggers this call chain. `@lru_cache` masks the cost, but every query still goes through `HuggingFaceEmbeddings` inference on CPU.

## 3. Vector Database Connection

**File:** `src/vector_store/chroma_client.py:11` — `get_vector_store()`, global `_vector_store` singleton.

Called from 10+ locations across the codebase:
- `chroma_client.py` (add, delete, stats)
- `retriever.py` (every get_retriever, rebuild_bm25)
- `pipeline.py` (all 4 entry points)
- `commands.py` (rebuild, stats)
- `console.py` (status bar)

**Problem:** The singleton pattern means any module can trigger Chroma initialization (and thus embedding model loading). The `reset_vector_store()` function clears the singleton but not the Chroma `delete_collection()` — the two-step dance in `commands.py:60-64` (`reset`, `get_vector_store`, `delete_collection`, `reset`) is fragile.

## 4. LLM Client Initialization

`ChatOpenAI` is created in **5 separate locations**, each with its own import of config:

| Location | Purpose | Created once? |
|----------|---------|---------------|
| `rag_agent.py:35` | Agent's internal model | Yes (inside `create_rag_agent()`) |
| `commands.py:128` | Chat history compression | No (on every `chat` command) |
| `console.py:93` | Chat history compression | Yes (background thread) |
| `graph_store/graph.py:243` | Graph extraction | No (on every `build_graph_store()`) |
| `graph_store/extraction_llm.py:62` | LLM batch extraction fallback | No (on every batch that fails) |

**Problem:**
- `commands.py:128` creates a *second* `ChatOpenAI` instance with identical config just for compression, even though `rag_agent.py` already creates one.
- The `DEEPSEEK_API_KEY` is read from config in every location, creating 5 copies of the key in memory.
- If DeepSeek base URL or model changes, 5 files need updating.

## 5. Does a Chat Request Re-Scan Documents?

**No.** Chat (`stream_rag_response`) touches only:
1. `get_retriever()` → `get_vector_store()` → Chroma (read-only)
2. `_bm25_retriever` global (BM25 pre-built at agent creation)

No file I/O to `DATA_DIR`, `data/external/`, or tracker happens during chat.

## 6. Does a Chat Request Re-Split or Re-Vectorize?

**No.** The chunks are already in ChromaDB (persistent). Chat only reads existing vectors.

However, `get_retriever()` at `retriever.py:19-34` creates a **new `Chroma.as_retriever()` object** on every invocation. This does not re-embed, but it does:
- Re-fetch the embedding model (cached)
- Re-connect to Chroma (singleton)
- Create a new retriever wrapper

## 7. Is the Retriever Rebuilt on Every Request?

**Partially.**

| Component | Lifetime | Rebuilt per request? |
|-----------|----------|----------------------|
| Chroma vector store | Global singleton | No |
| `Chroma.as_retriever()` | New per `get_retriever()` call | **Yes** (cheap wrapper) |
| BM25 retriever | Global `_bm25_retriever` | **No** (built once at agent load, rebuilt on data change) |
| `EnsembleRetriever` | New per `get_retriever()` call | **Yes** (wraps the two above) |

The wrapper creation is cheap (no I/O, no inference), so this is a minor concern.

## 8. How Is Session History Loaded?

**File:** `src/agent/chat_history.py`

```
save_history(messages, session_id=None)
  → JSON file: data/chat_history/session_YYYYMMDD_HHMMSS.json
  → returns stem (e.g. "session_20260730_220000")

load_history(session_id)
  → reads data/chat_history/{session_id}.json
  → returns list[dict] or None

compress_history(messages, llm, keep_rounds=10)
  → if user turns > keep_rounds: LLM-summarize oldest, keep recent 10 rounds
  → prepends [{"role": "system", "content": "[历史摘要] ..."}]

list_sessions()
  → glob data/chat_history/*.json, sorted reverse by mtime
```

**Two compression paths (duplicated logic):**
1. `commands.py:195-196` — during `cli chat` mode
2. `console.py:402-403` — during console chat mode

Both have the same `compress_history(messages, _chat_llm, keep_rounds=10)` call, but each creates its own `_chat_llm` reference.

## 9. Are API, Business Logic, and Infrastructure Mixed?

**Yes — the following layers are entangled:**

| Concern | Where it bleeds |
|---------|-----------------|
| Chroma singleton | Spans `chroma_client.py` (store), `retriever.py` (read), `pipeline.py` (write), `commands.py` (admin), `console.py` (status bar), `rag_agent.py` (preload) — 6 files reach into Chroma. |
| Embedding model | Initialized in `embedding.py`, called directly from `chroma_client.py`, `retriever.py`, `pipeline.py`, `rag_agent.py` — each passes it through different paths. |
| DeepSeek API key | Read from config in `rag_agent.py`, `commands.py`, `console.py`, `graph.py`, `extraction_llm.py` — 5 files. |
| Tool LLM reference | `tools.py` stores a global `_llm_for_tools`, set via `set_tool_llm()`. Any module can overwrite it. |
| `stream_rag_response()` | Lives in `rag_agent.py` but mixes iteration, tool detection, and response formatting. |
| Knowledge graph | `graph.py` builds from ingestion chunks (pipeline logic), but `build_graph_store()` calls `MarkdownLoader` itself — re-parsing files already parsed by the ingestion pipeline. |
| `console.py` | Inline `ChatOpenAI` creation, inline `compress_history`, inline DeepSeek config reads, inline `get_embedding_model`/`get_vector_store` calls for status bar. |

**Clean vs mixed file assessment:**

| File | Role | Purity |
|------|------|--------|
| `main.py` | CLI dispatcher | Clean (7 lines) |
| `config.py` | Flat env reader | Clean but no type validation |
| `embedding.py` | Model factory | Reasonable |
| `splitter.py` | Chunking factory | Clean |
| `loader.py` | File I/O | Reasonable |
| `tracker.py` | File state tracking | Clean |
| `chat_history.py` | Session persistence | Clean |
| `grading.py` | Relevance grading (prompt) | Clean |
| `rewrite.py` | Query rewriting (prompt) | Clean |
| `retriever.py` | Retriever factory + BM25 singleton | Mixed (singleton module state) |
| `chroma_client.py` | Vector store singleton | Mixed (global, 5 responsibilities) |
| `pipeline.py` | Orchestration | **Heavy mix** (6 steps, graph building inline) |
| `graph.py` | Knowledge graph + build orchestrator | **Mixed** (data model + pipeline + I/O) |
| `extraction.py` | Jieba extraction | Clean |
| `extraction_llm.py` | LLM extraction + fallback | Reasonable |
| `tools.py` | Agent tools | **Mixed** (retrieval, grading, compression, graph — 4 concerns) |
| `rag_agent.py` | Agent factory + stream helper | Reasonable |
| `commands.py` | CLI handlers | **Mixed** (commands + inline LLM init + inline stream) |
| `console.py` | TUI loop | **Mixed** (UI + agent loading + LLM init + compression) |

## 10. Background Task Issues

**Daemon thread for agent loading** (`console.py:89-101`):

| Aspect | Status |
|--------|--------|
| **Start** | One thread, started once per `run_console()` call. Fine. |
| **Stop** | Daemon thread — does not block process exit. Fine for shutdown, but no cleanup path. |
| **Failure** | Exception caught and stored in `_agent_result`. Agent-dependent commands show "加载失败". No retry. |
| **Duplicate** | `run_console()` is not reentrant-friendly. Second call spawns a second loading thread. |
| **Resource** | If loading fails after model download, the model stays in HuggingFace cache but won't be reused until next manual retry. |
| **Race** | `_agent_ready` Event + agent result stored as module global. Safe for single `run_console()`. |

**Repeated `build_graph_store()` calls:**
- Every `/ingest`, `/add`, `cli update-file`, `cli update` calls `build_graph_store()` or `KnowledgeGraph.add_chunks()`.
- Each call re-parses all documents from disk (via `MarkdownLoader`) — even for incremental adds where only 1 file changed.
- `build_graph_store()` at `graph.py:221-252` has its own document loading loop, duplicating the load done by `run_ingestion()`.

**No cache for graph search results:**
- Every call to `search_graph()` walks the NetworkX subgraph. No memoization for repeated queries.
