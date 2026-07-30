# File-Level Refactor Plan

## Principles

1. Each file owns exactly one concern.
2. The LLM client is created in exactly one place.
3. Embedding model + Chroma are accessed through a service layer, not directly from business logic.
4. Pipeline steps are composable (load → split → embed → store are independent functions, not one `run_ingestion` monolith).
5. Graph building does not re-parse documents already parsed by the ingestion pipeline.

---

## Phase 1 — Service Layer (no behavior change)

### 1a. Extract `LLMClient` Provider

**Replace 5 scattered `ChatOpenAI` instantiations with one factory.**

| Current location | Replace with |
|-----------------|--------------|
| `rag_agent.py:35` | `from src.llm import get_llm` |
| `commands.py:128` | `from src.llm import get_llm` |
| `console.py:93` | `from src.llm import get_llm` |
| `graph.py:243` | `from src.llm import get_llm` |
| `extraction_llm.py:62-68` | Accept llm param (already does); callers pass it |

**New file:** `src/llm/__init__.py` or `src/llm/client.py`
```
get_llm(temperature=0) → ChatOpenAI  [cached; always returns same singleton]
get_compression_llm() → ChatOpenAI   [separate for rate-limit isolation, optional]
```

**Removes:** 5 copies of `ChatOpenAI(model=LLM_MODEL, api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_API_BASE, temperature=0)`

### 1b. Extract `VectorStoreService`

**Replace direct `chroma_client` singleton + `retriever` singleton access from business logic.**

**New file:** `src/vector_store/service.py`
```
class VectorStoreService:
    get_retriever(k)       → wraps get_vector_store().as_retriever()
    add_documents(chunks)  → add with progress
    delete_by_source(name) → delete from Chroma
    rebuild_bm25()         → rebuild global BM25
    get_stats()            → collection stats
    reset()                → clear + delete + reset
```

**Callers migrate:**
- `pipeline.py` → `VectorStoreService`
- `tools.py` → `VectorStoreService`
- `commands.py` → `VectorStoreService`
- `console.py` → `VectorStoreService`

### 1c. Extract `GraphService`

**New file:** `src/graph_store/service.py`
```
class GraphService:
    build_from_chunks(chunks, llm)  → no re-loading from disk
    build_from_disk(DATA_DIR, EXTERNAL_DIR)  → one-stop for CLI
    search(query)                   → delegates to KnowledgeGraph
    get_stats()                     → entity/relation counts
    add_chunks(chunks, llm)         → incremental update
```

**Callers migrate:**
- `pipeline.py` → `GraphService.build_from_chunks(chunks)` instead of `build_graph_store()`.
- `commands.py` → `GraphService.build_from_disk()`.
- `console.py` → `GraphService.get_stats()`.

## Phase 2 — Pipeline Refactor

### 2a. Decompose `pipeline.py`

**Current:** One file with 4 `run_*` functions, each duplicating the 6-step pipeline.

**Target:** One orchestrator with composable steps.

```
src/ingestion/
  loader.py        ← keep
  splitter.py      ← keep
  tracker.py       ← keep
  pipeline.py      ← thin orchestrator only
  steps/
    load_step.py   ← load files → list[Document]
    split_step.py  ← split documents → list[Document]
    store_step.py  ← embed + add to Chroma + rebuild BM25
    graph_step.py  ← build/update KnowledgeGraph from chunks
```

Each step is a standalone function accepting `echo_fn`. The orchestrator becomes:

```python
def run_ingestion(data_dir, ..., echo_fn=print):
    docs = load_step(data_dir, echo_fn=echo_fn)
    chunks = split_step(docs, chunk_size, chunk_overlap, echo_fn=echo_fn)
    store_step(chunks, echo_fn=echo_fn)
    graph_step(chunks, echo_fn=echo_fn)
    update_tracker("internal", data_dir)
    return len(chunks)
```

### 2b. Incremental Graph Update

**Change:** `graph_step` receives only the changed chunks (not all documents).

Currently `build_graph_store()` at `graph.py:221` re-loads everything. Change to:

```python
def graph_step(chunks, echo_fn=print):
    if not ENABLE_GRAPH:
        return
    kg = KnowledgeGraph(echo_fn=echo_fn)
    kg.add_chunks(chunks, llm=get_llm() if ENABLE_GRAPH_LLM_EXTRACTION else None)
    kg.save()
    set_graph(kg)
```

This way incremental update only re-extracts for the changed files.

### 2c. Eliminate Duplicate Load in `build_graph_store()`

**Current:** `graph.py:221-252` calls `MarkdownLoader` + `load_path` to parse all documents a second time.

**Target:** `build_graph_store()` becomes a thin CLI convenience:

```python
# commands.py
@cli.command()
def build_graph():
    chunks = get_vector_store().get_all()  # reuse already-stored chunks
    GraphService.build_from_chunks(chunks)
```

Or simply remove the separate `cli build-graph` command and fold it into ingestion, since vector store already has the data.

## Phase 3 — Performance

### 3a. Parallelize Grading

**File:** `src/agent/tools.py:26-29`

**Change:** Replace sequential `for doc in docs: grade_document(...)` with concurrent calls:

```python
from concurrent.futures import ThreadPoolExecutor, as_completed

def _grade(query, docs, llm):
    if not (ENABLE_GRADING and llm):
        return docs[:TOP_K]
    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = {pool.submit(grade_document, query, d.page_content, llm): d for d in docs}
        relevant = [futures[f] for f in as_completed(futures) if f.result()]
    return relevant[:TOP_K] if relevant else docs[:TOP_K]
```

Same pattern for `_compress()`.

**Risk:** DeepSeek API rate limits (5 requests/s for free tier). Add `sleep(0.2)` between batches if needed.

### 3b. Batch Embedding for Retriever

**Current:** `get_retriever()` calls `get_embedding_model()` on every invocation. The actual embedding happens inside Chroma's `similarity_search`, which embeds the query string.

**Change (minor):** Ensure the retriever reuses the same embedding model reference:

Already cached by `@lru_cache`, so this is mostly fine. Worth verifying that `Chroma.as_retriever()` doesn't create a new embedding wrapper.

### 3c. Lazy BM25 Rebuild

**Current:** BM25 rebuilt after every `/add`, `/remove`, `cli update-file`.

**Change:** Defer BM25 rebuild until next query if a dirty flag is set:

```python
_bm25_dirty = False

def rebuild_bm25(store):
    global _bm25_retriever, _bm25_dirty
    _bm25_dirty = True

def get_retriever(k):
    if _bm25_dirty:
        _rebuild_bm25_impl(get_vector_store())
        _bm25_dirty = False
    ...
```

This means `/add` returns instantly, and the rebuild cost shifts to the first query after the add.

### 3d. Embedding Query Cache

**File:** `src/agent/tools.py` or `src/retrieval/retriever.py`

Add an LRU cache for recent query embeddings:

```python
from functools import lru_cache

@lru_cache(maxsize=64)
def cached_query(query: str):
    return get_embedding_model().embed_query(query)
```

This requires modifying Chroma's retriever to accept pre-computed embeddings, or wrapping the retriever. Alternatively, keep it simple and skip — the embedding is only ~50-200ms.

### 3e. Reduce Status Bar Overhead

**File:** `console.py:104-135`

Wrap Chroma stats and graph stats in a `@lru_cache` with `maxsize=1` and a TTL of 5 seconds, or simply call them only on explicit `/stats`, not on every redraw.

## Phase 4 — Structural

### 4a. Move Console Compression to Shared Service

**Current:** `commands.py:195` and `console.py:402` both call:

```python
raw_history = compress_history(raw_history, _chat_llm, keep_rounds=10)
```

each with their own `_chat_llm` reference.

**Change:** Both use a single `get_compression_llm()` from the LLM service.

### 4b. Remove Inline DeepSeek Key from Console

**File:** `console.py:12`

**Current:** `from config import LLM_MODEL, DEEPSEEK_API_KEY, DEEPSEEK_API_BASE`

**Change:** Console should not know about API keys. Delegate all LLM creation to `src/llm/client.py`.

### 4c. `stream_rag_response()` → Separate Module

**File:** `rag_agent.py:56-70`

This function mixes agent streaming with tool-detection logic and response formatting. Extract to `src/agent/stream.py`.

## File Dependency Graph (Target)

```
main.py
  └── src/
      ├── cli/
      │   ├── commands.py    → LLMService, VectorStoreService, GraphService, pipeline
      │   └── console.py     → LLMService, VectorStoreService, pipeline
      │
      ├── llm/
      │   └── client.py      → config.py (only place that reads DEEPSEEK keys)
      │
      ├── ingestion/
      │   ├── loader.py      → file I/O
      │   ├── splitter.py    → chunking
      │   ├── tracker.py     → file_tracker.json
      │   ├── pipeline.py    → orchestrator (calls steps/)
      │   └── steps/
      │       ├── load_step.py
      │       ├── split_step.py
      │       ├── store_step.py   → VectorStoreService
      │       └── graph_step.py   → GraphService
      │
      ├── vector_store/
      │   ├── embedding.py   → model factory (keep)
      │   ├── chroma_client.py → low-level Chroma singleton (keep but internal)
      │   └── service.py     → public API (get_retriever, add, delete, stats)
      │
      ├── retrieval/
      │   ├── retriever.py   → get_retriever (keep, thin)
      │   ├── grading.py     → prompt (keep)
      │   └── rewrite.py     → prompt (keep)
      │
      ├── graph_store/
      │   ├── graph.py       → KnowledgeGraph data model (keep)
      │   ├── extraction.py  → jieba (keep)
      │   ├── extraction_llm.py → LLM extraction (keep)
      │   ├── retriever.py   → search_graph singleton (keep)
      │   └── service.py     → public API (new)
      │
      └── agent/
          ├── tools.py       → @tool definitions (keep, but thin)
          ├── rag_agent.py   → create_deep_agent factory (keep)
          ├── stream.py      → streaming response (extract from rag_agent.py)
          └── chat_history.py → session persistence (keep)
```

## Migration Order

| Step | Files changed | Risk | Reason |
|------|--------------|------|--------|
| 1 | New `src/llm/client.py`, edit 5 consumers | Low | Mechanical replacement, no logic change |
| 2 | New `src/vector_store/service.py`, edit 5 consumers | Low | Wraps existing singleton |
| 3 | New `src/graph_store/service.py`, edit 3 consumers | Low | Wraps existing logic |
| 4 | Refactor `pipeline.py` → `steps/` (4 new files) | Medium | Splits monolith; test coverage critical |
| 5 | Incremental graph update | Medium | Changes graph building behavior |
| 6 | Remove duplicate load from `build_graph_store()` | Low | Dead code removal |
| 7 | Parallelize grading + compression | Medium | Concurrency introduces new failure modes |
| 8 | Lazy BM25 rebuild | Low | Atomic swap of rebuild trigger |
| 9 | Reduce status bar overhead | Low | Cache wrapper |
| 10 | Consolidate compression call sites | Low | Mechanical |
| 11 | Remove API key from console.py | Low | Mechanical |
| 12 | Extract `stream.py` | Low | Mechanical |

## Files Not Recommended for Change

| File | Reason |
|------|--------|
| `main.py` | Minimal, clean, serves its purpose |
| `config.py` | Fine for current scale; validate types if refactored |
| `embedding.py` | Single-responsibility; keep |
| `loader.py` | Single-responsibility; keep |
| `splitter.py` | Single-responsibility; keep |
| `tracker.py` | Single-responsibility; keep |
| `chat_history.py` | Single-responsibility; keep |
| `grading.py` | Single-responsibility; keep |
| `rewrite.py` | Single-responsibility; keep |
| `extraction.py` | Pure jieba logic; keep |
| `extraction_llm.py` | LLM extraction + fallback; keep (accept `llm` param already) |
