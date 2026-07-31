# CLI Design: `kb` — Knowledge Base Command Line

## Overview

`kb` is a unified CLI for the LangChain RAG 知识库 system. Every command outputs
data to **stdout**, diagnostics/errors/progress to **stderr**, and returns semantic
exit codes. All operations have non-interactive flag equivalents.

Entry point: `kb <command> [options]`

---

## Command Tree

```
kb
├── serve        Start FastAPI + MCP service
├── index        Index file(s) or directory into vector store
├── search       Search knowledge base
├── chat         Ask a question (RAG-powered)
├── status       Show service / task / index status
├── doctor       Diagnose configuration, model, vector store, deps
└── config       View or validate configuration
```

---

## Per-Command Design

### `kb serve`

Start the FastAPI HTTP server (API v1 + MCP endpoint).

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--host` | string | `127.0.0.1` | Listen address |
| `--port` | int | `8000` | Listen port |
| `--reload` | flag | false | Auto-reload on file change (dev only) |
| `--json` | flag | false | Structured JSON output |

**Behavior:**
1. Load `create_app()` from `src.api.app`
2. Start `uvicorn` with the ASGI app
3. Log startup info to stderr
4. On Ctrl-C, shutdown gracefully

**Output (stdout):**
```
Listening on http://127.0.0.1:8000
MCP endpoint: http://127.0.0.1:8000/mcp
```

With `--json`:
```json
{"status": "ok", "data": {"url": "http://127.0.0.1:8000", "mcp": "http://127.0.0.1:8000/mcp"}}
```

**Exit codes:** 0 = started, 75 = port in use (transient), 78 = config error.

---

### `kb index`

Index one or more documents into the knowledge base. Wraps `run_ingestion`,
`run_add_path`, `run_single_file_update`.

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--path` | string | — | File or directory to index (if omitted, re-index DATA_DIR) |
| `--chunk-size` | int | *config* | Override chunk size |
| `--chunk-overlap` | int | *config* | Override chunk overlap |
| `--rebuild` | flag | false | Drop collection before indexing (dangerous) |
| `--incremental` | flag | false | Only index changed/new files (default: full scan) |
| `--dry-run` | flag | false | Show what would be indexed without writing |
| `--json` | flag | false | Structured JSON output |

**Rules:**
- `--dry-run` + `--rebuild` prints "Would drop collection + re-index N files"
  to stdout, does nothing
- `--path` can be a single file or directory; directory is walked recursively
- Without `--path`, indexes the configured `DATA_DIR`
- Progress bar to stderr (only when TTY)

**Output (stdout):**
```
Indexed 47 documents (1250 chunks) from ./data/docs
```

With `--json`:
```json
{"status": "ok", "data": {"files": 47, "chunks": 1250, "source": "./data/docs"}}
```

**Exit codes:** 0 = success, 2 = path not found, 78 = config error.

---

### `kb search`

Search the knowledge base and return matching chunks.

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `query` | positional | — | Search query (required) |
| `--top-k` | int | 5 | Number of results |
| `--json` | flag | false | Structured JSON output |
| `--fields` | string | — | Comma-separated output fields: source,content,score |

**Behavior:**
- Calls `VectorStoreService().get_retriever(k=top_k)` then invokes the retriever
- Formats results as text table (TTY) or plain lines (pipe)

**Human output (stdout):**
```
1. (docs/langchain.md) score=0.92
   LangChain is a framework for developing applications powered by language models...

2. (docs/rag.md) score=0.85
   RAG stands for Retrieval-Augmented Generation...
```

With `--json`:
```json
{"status": "ok", "data": [{"source": "docs/langchain.md", "content": "...", "score": 0.92}], "total": 2}
```

**Exit codes:** 0 = always (empty results are success).

---

### `kb chat`

Ask a question and get a RAG-powered answer.

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `query` | positional | — | Question (required, or use `--query`) |
| `--query` | string | — | Alternative to positional arg |
| `--session` | string | — | Continue existing session ID |
| `--list-sessions` | flag | false | List past sessions and exit |
| `--no-stream` | flag | false | Non-streaming mode (wait for full answer) |
| `--json` | flag | false | Structured JSON output |

**Behavior:**
- Without `--session`: starts new session
- With `--session <id>`: loads history from `<id>.json` via `load_history()`
- With `--list-sessions`: calls `list_sessions()`, prints table
- Calls `create_rag_agent()` (one-time init on first call) then
  `stream_rag_response()`
- Saves history on exit

**Human output (stdout):** Streaming answer text.

With `--json` (non-streaming):
```json
{"status": "ok", "data": {"answer": "...", "session_id": "session_20260731_120000", "turns": 1}}
```

**Exit codes:** 0 = success, 75 = API timeout (retryable), 78 = missing API key.

---

### `kb status`

Show health and status of all system components.

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--watch` | flag | false | Continuously refresh every 2s (requires TTY) |
| `--json` | flag | false | Structured JSON output |

**Behavior:**
- Calls `VectorStoreService().get_stats()`, `GraphService().get_stats()`,
  `get_task_manager()`
- Also checks: embedding model loaded, Chroma accessible, BM25 index exists
- Prints a dashboard-style summary table (TTY) or line format (pipe)

**Human output (stdout):**
```
Vector Store:     healthy  (1250 chunks, 47 sources)
Knowledge Graph:  healthy  (234 entities, 89 relations)
BM25 Index:       ready    (1250 docs)
Embedding Model:  loaded   (bge-small-zh)
API:              not running
Pending Tasks:    none
```

With `--json`:
```json
{"status": "ok", "data": {"vector_store": {"count": 1250, "sources": 47}, "graph": {"entities": 234, "relations": 89}, "bm25": "ready", "embedding": "bge-small-zh", "api": "stopped", "tasks": []}}
```

**Exit codes:** 0 = all healthy, 1 = one or more components unhealthy.

---

### `kb doctor`

Run comprehensive diagnostics and report issues.

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--verbose` | flag | false | Show detailed diagnostics per component |
| `--fix` | flag | false | Attempt auto-fix for detected issues |
| `--json` | flag | false | Structured JSON output |

**Checks performed (in order):**

| # | Check | What it verifies |
|---|-------|-----------------|
| 1 | `.env` exists | Config file presence |
| 2 | API Key set | `DEEPSEEK_API_KEY` non-empty |
| 3 | API Key works | Calls `get_llm(0).invoke("hi")` |
| 4 | Embedding model | `get_embedding_model()` loads |
| 5 | Vector store | `get_vector_store()` accessible |
| 6 | BM25 index | Persisted BM25 file exists |
| 7 | Chroma DB dir | `CHROMA_PERSIST_DIR` exists |
| 8 | DATA_DIR | `DATA_DIR` exists, has supported files |
| 9 | Graph store | `GraphService().get_stats()` responds |
| 10 | Dependencies | Key packages importable |

**Human output (stdout):**
```
✔ .env found
✔ DEEPSEEK_API_KEY is set
✔ Embedding model loads (bge-small-zh)
✖ BM25 index missing — run: kb index --incremental
✔ Chroma DB accessible
✔ DATA_DIR exists (47 files)
✔ Graph store responds
✔ All key dependencies importable

Summary: 7/8 checks passed
1 issue found — run: kb index --incremental
```

With `--json`:
```json
{"status": "ok", "data": {"checks": [{"name": "env_file", "passed": true}, ...], "passed": 7, "total": 8, "fixes": ["kb index --incremental"]}}
```

**Exit codes:** 0 = all pass, 1 = one or more checks failed,
78 = critical config missing.

---

### `kb config`

View or validate configuration.

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--key` | string | — | Show a single config key |
| `--validate` | flag | false | Validate current config and report issues |
| `--show-origin` | flag | false | Show where each value comes from |
| `--json` | flag | false | Structured JSON output |

**Note:** Read-only (view + validate). Config changes are done via `.env` editing.
This follows Unix composability — `kb config` shows what is, not what should be.

**Human output (stdout):**
```
Key                              Value                  Source
────────────────────────────────────────────────────────────────
DATA_DIR                         C:\Users\...\data      env
EMBEDDING_MODEL                  bge-small-zh           env
CHUNK_SIZE                       500                    default
ENABLE_GRAPH                     true                   env
DEEPSEEK_API_KEY                 ****sk-...             env (set)
```

With `--validate`:
```
✔ All required keys present
✔ DATA_DIR exists
✔ CHUNK_SIZE = 500 (valid range: 100–2000)
✔ TOP_K = 5 (valid range: 1–50)
⚠ DEEPSEEK_API_KEY: using default (check .env)
```

With `--json`:
```json
{"status": "ok", "data": {"keys": [{"key": "DATA_DIR", "value": "C:\\...", "source": "env"}], "valid": true, "warnings": []}}
```

**Exit codes:** 0 = valid, 78 = invalid config.

---

## Global Flags

| Flag | Effect |
|------|--------|
| `--help` / `-h` | Show help and exit |
| `--json` | Structured JSON output |
| `--quiet` / `-q` | Suppress stderr progress messages |
| `--no-color` | Disable ANSI colors |
| `--version` | Show version and exit |

---

## Exit Code Table

| Code | Meaning | When |
|------|---------|------|
| 0 | Success | Operation completed |
| 1 | General failure | Catch-all error |
| 2 | Usage error | Bad args, unknown flags |
| 3 | Resource not found | Path, file, session not found |
| 4 | Permission denied | Cannot write to configured dirs |
| 5 | Conflict | Resource already exists |
| 75 | Temporary failure | Network timeout — retryable |
| 78 | Configuration error | Missing API key, invalid config |

---

## JSON Envelope

Every `--json` response uses this shape:

```json
{
  "status": "ok",
  "data": { ... },
  "error": {
    "code": "CONFIG_ERROR",
    "message": "DEEPSEEK_API_KEY is not set",
    "fix": "Add DEEPSEEK_API_KEY=sk-... to .env",
    "transient": false
  },
  "warnings": ["..."],
  "next_steps": ["kb config --validate"]
}
```

---

## stdout / stderr Discipline

| Stream | Content | Examples |
|--------|---------|----------|
| stdout | Primary output only | Search results, status table, config dump, answer text, JSON |
| stderr | Everything else | Errors, warnings, progress bars, logs, debug info, prompts |

All commands detect `isatty(stdout)` to decide formatting:
- **TTY:** Tables, colors, progress bars
- **Pipe / redirect:** Plain text, no ANSI, compact format

---

## Mapping to Existing Services

| Command | Backend Call |
|---------|-------------|
| `serve` | `src.api.app.create_app()` + `uvicorn.run()` |
| `index` | `run_ingestion()`, `run_add_path()`, `run_single_file_update()` |
| `search` | `VectorStoreService().get_retriever()` invoke |
| `chat` | `create_rag_agent()` + `stream_rag_response()` |
| `status` | `VectorStoreService().get_stats()`, `GraphService().get_stats()`, `get_task_manager()` |
| `doctor` | `get_embedding_model()`, `get_llm()`, service health checks |
| `config` | `config.py` variables, `dotenv` values |

No new business logic — CLI is a thin orchestration layer over existing Services.

---

## Composable Pipeline Example

```bash
# Check status before any operation
kb status --json | jq '.data'

# Index new docs with dry-run preview
kb index --path /docs/new-feature.md --dry-run --json | jq '.data.chunks'

# Index for real
kb index --path /docs/new-feature.md

# Search to verify
kb search "new feature setup"

# Chat session
kb chat "how does the new feature work?" --session session_123

# Full health check
kb doctor --verbose --json | jq '.data.checks[] | select(.passed==false)'
```
