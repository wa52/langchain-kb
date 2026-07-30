# Performance Risk Report

## Hot Path Analysis

### Critical Path: Chat Query → Response

For every user question in chat mode, the following executes:

```
user input
 → stream_rag_response()
   → agent.stream() → retrieve_knowledge.invoke()
     → _search()
       → get_embedding_model()     [@lru_cache hit → fast]
       → get_vector_store()        [singleton hit → fast]
       → Chroma.as_retriever()     [new object, cheap]
       → retriever.invoke(query)   [Chroma similarity_search with MMR]
         → embedding inference on CPU  [~50-200ms for bge-small-zh]
         → HNSW vector search          [~5-20ms for 2k vectors]
     → _grade()                    [if ENABLE_GRADING]
       → ChatOpenAI invoke per doc up to TOP_K*3=15 docs
       → 15 sequential LLM calls   [~150ms × 15 = ~2.25s]
       → (if all irrelevant) rewrite_question() → 1 more LLM call
     → _compress()                 [if ENABLE_CONTEXT_COMPRESSION]
       → ChatOpenAI invoke per result doc  [~150ms × up to 5 = ~0.75s]
     → search_graph()              [if ENABLE_GRAPH]
       → NetworkX subgraph walk    [~1-10ms]
```

**Estimated latency per chat turn (all features ON):**

| Step | Time | Type |
|------|------|------|
| Embedding inference | 50-200ms | CPU-bound |
| Chroma search | 5-20ms | I/O-bound |
| Grading (15 docs) | 1.5-3s | LLM-bound (sequential × 15) |
| Compression (5 docs) | 0.5-1s | LLM-bound (sequential × 5) |
| Graph search | 1-10ms | CPU-bound |
| Agent LLM response | 2-10s | LLM-bound |
| **Total** | **~4-14s** | |

### Risks

#### P1 — Sequential LLM Calls in Grading (`tools.py:26-29`)

`grade_document()` calls `llm.invoke()` per document in a `for` loop — 15 sequential DeepSeek API calls. This is the single largest latency contributor.

- Same pattern in `_compress()` (5 calls, `tools.py:52`).
- No batching, no concurrency, no caching.
- If DeepSeek rate-limits one call, all subsequent calls in the loop also fail.

#### P1 — Embedding Model Loaded for Every Query Flow

`get_retriever()` at `retriever.py:21` calls `get_embedding_model()` unconditionally. While `@lru_cache` makes this fast after first load, the `HuggingFaceEmbeddings` object is re-obtained (still cached). The actual cost is the `embed_documents()` / `embed_query()` call that Chroma's retriever triggers on each query.

For `bge-small-zh` (384-dim, ~33MB): ~50-200ms per query on CPU.
For `bge-m3` (1024-dim, ~2.2GB): ~500ms-2s per query on CPU.

#### P2 — BM25 Index Rebuilt After Every Data Change

`rebuild_bm25()` at `retriever.py:37` fetches all documents from Chroma in paginated batches (500 at a time), then creates an entirely new `BM25Retriever.from_texts()`. For ~2000 chunks:
- 4 Chroma read requests
- Full BM25 tokenization + indexing in memory
- ~2-5s on moderate hardware

This runs after every `/add`, `/remove`, `/ingest`, `/rebuild`, `cli update`, `cli update-file`. For small changes (1 file), this is wasteful.

#### P2 — Graph Store Rebuilt from Scratch on Every Ingestion

`run_ingestion()` calls `build_graph_store()` which re-parses ALL documents from disk, re-extracts ALL entities, re-builds the full NetworkX graph. For incremental data changes, only the changed files should be re-processed.

`build_graph_store()` at `graph.py:221-252` duplicates the document loading that `run_ingestion()` already did — it calls `MarkdownLoader` a second time.

#### P2 — Context Compression on Every Chat Turn

`compress_history()` at `chat_history.py:35` runs after every assistant response. For a conversation with 12 turns, it makes one LLM call to summarize the oldest 2 turns. This is fast but unnecessary if the conversation hasn't grown beyond `keep_rounds`.

The real concern: both `commands.py:195` and `console.py:402` call this independently, each with their own `ChatOpenAI` instance.

#### P3 — Knowledge Graph LLM Extraction Creates New `ChatOpenAI` Per Call

`extract_entities_llm_batch()` at `extraction_llm.py:62` creates a brand new `ChatOpenAI` if none is passed. This loses connection pooling and incurs TCP handshake overhead.

#### P3 — `console.py` Status Bar Hits Chroma and Graph on Every Redraw

`get_status_bar()` at `console.py:104` calls:
- `list_all_files()` (JSON I/O)
- `get_collection_stats()` (Chroma count + paginated metadata read)
- `get_graph().graph.number_of_nodes()` (NetworkX)

The status bar is redrawn after every command and after every chat response. This adds ~50-300ms of overhead to every interaction.

#### P4 — Concurrent Chat Requests Not Possible

Because `_vector_store`, `_bm25_retriever`, and `_kg` are module-level globals, and `_llm_for_tools` is a module-level global in `tools.py`, concurrent access would race. The console is single-user, so this is acceptable, but it prevents future async/multi-user support.

#### P4 — No Embedding Cache for Repeated Queries

If the user asks two similar questions within a session, both trigger the full embedding inference. There is no query-level embedding cache.

## Summary Table

| # | Risk | Severity | File(s) | Cause |
|---|------|----------|---------|-------|
| 1 | Sequential LLM grading (15 calls) | P1 | `tools.py:26-29` | Per-doc `for` loop with `llm.invoke()` |
| 2 | Embedding inference per query | P1 | `retriever.py:21` | `get_embedding_model()` on every `get_retriever()` |
| 3 | BM25 rebuilt from scratch after every change | P2 | `retriever.py:37`, `pipeline.py` | No BM25 append/update, only full rebuild |
| 4 | Graph store re-parses all docs on each ingress | P2 | `graph.py:221-252` | `build_graph_store()` has own load loop |
| 5 | Duplicate ChatOpenAI instances | P2 | `commands.py:128`, `console.py:93` | 5 places create LLM client |
| 6 | Status bar I/O on every command | P3 | `console.py:104-135` | Chroma + file tracker + graph on every redraw |
| 7 | Singleton globals prevent concurrency | P4 | Multiple | `_vector_store`, `_bm25_retriever`, `_llm_for_tools` |
| 8 | No query embedding cache | P4 | `tools.py` | Same query re-embeds every time |
