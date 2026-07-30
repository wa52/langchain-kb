# AGENTS.md — LangChain RAG 知识库系统

## Quick start

```powershell
pip install -r requirements.txt
python main.py ingest          # 1st: build vector index (1879 chunks from ~81 files)
python main.py                 # interactive console with status bar + 14 slash commands
python main.py search <query>  # vector search only
```

## Entrypoints

| Entry | Trigger | What loads |
|-------|---------|------------|
| `python main.py` (no args) | `run_console()` in `console.py` | embedding model + agent + LLM |
| `python main.py <cmd>` | Click CLI in `commands.py` | depends on cmd |

## Console slash commands (`/help` lists all 14)

| Command | Action |
|---------|--------|
| `/add <path>` | Copy file/dir to `data/external/`, index, show `[0%→100%]` progress bar |
| `/ingest` | Full re-import from DATA_DIR |
| `/rebuild` | Drop collection + re-import (asks confirm) |
| `/mode [llm\|jieba]` | Toggle graph extraction backend (persisted to `.env`) |
| `/new` `/resume <id>` `/sessions` | Chat session management |
| `/stats` `/config` `/files` `/clear` `/exit` | Info & utility |

## Architecture

```
main.py
  ├─ src/cli/
  │    commands.py   — Click CLI (16 commands) + echo() helper
  │    console.py    — interactive console loop, slash commands, streaming chat
  ├─ src/ingestion/
  │    loader.py     — .md/.txt/.pdf loader, MarkdownLoader(echo_fn=print)
  │    splitter.py   — RecursiveCharacterTextSplitter, markdown-aware separators
  │    pipeline.py   — run_ingestion/run_add_path/… all accept echo_fn=print
  │    tracker.py    — file_tracker.json (md5 of mtime+size) for incremental
  ├─ src/vector_store/
  │    chroma_client.py — ChromaDB singleton, add_documents_with_progress(echo_fn=print)
  │    embedding.py     — @lru_cache get_embedding_model(), bge-small-zh default
  ├─ src/retrieval/
  │    retriever.py  — MMR + BM25 hybrid via EnsembleRetriever
  │    grading.py    — relevance grading (optional)
  │    rewrite.py    — query rewrite (optional)
  ├─ src/graph_store/
  │    graph.py      — NetworkX graph, persistence to data/knowledge_graph.json
  │    extraction.py — jieba-based entity/relation extraction (fallback)
  │    extraction_llm.py — DeepSeek batch extraction + jieba fallback
  │    retriever.py  — graph_search(query) → entities+relations
  └─ src/agent/
       tools.py       — @tool retrieve_knowledge (unified hybrid + graph)
       rag_agent.py   — Deep Agent factory, pre-loads embedding in main thread
       chat_history.py — JSON persistence, compress_history(keep_rounds=10)
```

## Tests

```powershell
python -m pytest tests/         # 51 tests (~40s)
python -m pytest tests/test_console.py -v
python -m pytest tests/test_progress.py -v  # echo_fn + progress bar tests
```

- **No API key needed** for most tests — mock `run_add_path`/`run_remove`, mock ChromaDB
- Tests that call `get_embedding_model()` take ~15s to load the model at collection time

## echo_fn pattern (progress injection)

All pipeline/logging functions accept `echo_fn: callable = print` to allow output routing:

```python
def run_add_path(…, echo_fn: callable = print): …
def add_documents_with_progress(…, echo_fn: callable = print): …
def rebuild_bm25(store, echo_fn: callable = print): …
```

- **CLI commands** (`commands.py`) pass `echo_fn=echo` (supports `end=""` for `\r` overwrite)
- **Console** (`console.py`) also passes `echo_fn=echo` (imported from `commands.py`)
- **Tests** pass `echo_fn=mock_fn` to assert progress calls

The `echo()` function signature: `echo(msg: str = "", end: str = "\n")` — wraps `print()` with UnicodeEncodeError fallback.

## Progress bar format

```
[ 15%] ##########..........  75/500  (2.3s, 32 ch/s)
```

ASCII only (`#` / `.`), 20 chars wide, `\r` overwrite same line. Safe in GBK terminals.

## Critical gotchas

1. **GBK terminal** — Windows `chs` codepage cannot render Unicode. `main.py` wraps stdout with `utf-8/replace`. `echo()` catches `UnicodeEncodeError`. Never `rich.console.Markdown`.

2. **HuggingFace mirror** — `HF_ENDPOINT=https://hf-mirror.com` set in `config.py:18-19` and `embedding.py:6` at module level (must be before `huggingface_hub` import). The model weights ~33MB (bge-small-zh) or ~2.2GB (bge-m3).

3. **Pre-load embedding before agent** — `huggingface_hub` httpx client breaks in thread pool. Always call `get_embedding_model()` + `get_vector_store()` in main thread before `create_rag_agent()`. Handled in `rag_agent.py:23-24`.

4. **DeepSeek = OpenAI‑compatible** — model `deepseek-chat`, client `ChatOpenAI(base_url=https://api.deepseek.com)`. Never native DeepSeek SDK.

5. **`EnsembleRetriever` from `langchain_classic`** — not `langchain.retrievers`. Imported in `retriever.py:4`. BM25 index rebuilt after every data change.

6. **`handle_command` has no try/except** — exceptions from `/add`/`/remove`/etc. crash the console. Test before deployment.

7. **`echo("助手: ", end="")` (console.py:296)** — only works because `echo()` now accepts `end` param. Before the change it was a latent bug.

## Config (.env)

| Key | Default | Description |
|-----|---------|-------------|
| `DATA_DIR` | `C:\Users\SJ\Desktop\md\langchain_data` | Source document directory |
| `EMBEDDING_MODEL` | `bge-small-zh` | `bge-m3`, `bge-small-zh`, `bge-base-zh`, or `openai` |
| `LLM_MODEL` | `deepseek-chat` | Model name for ChatOpenAI |
| `DEEPSEEK_API_KEY` | (set in .env) | DeepSeek / OpenAI-compatible API key |
| `ENABLE_GRAPH_LLM_EXTRACTION` | `false` | Use DeepSeek (instead of jieba) for graph extraction |
| `ENABLE_CONTEXT_COMPRESSION` | `true` | Compress chat history via LLM summary (keeps last 10 rounds) |
| `ENABLE_HYBRID_SEARCH` | `true` | BM25 + vector ensemble retrieval |
| `ENABLE_GRADING` / `ENABLE_REWRITE` | `true` / `true` | Relevance grading / query rewrite |
| `EMBED_SERVER_ENABLED` | (not yet) | Planned: embedding server to avoid per-command model load |

## Change model

```powershell
# .env: EMBEDDING_MODEL=bge-m3 → python main.py rebuild
```

## Dependencies

Key: `deepagents`, `langchain`, `langchain-chroma`, `langchain-huggingface`, `langchain-openai`, `prompt_toolkit`, `chromadb`, `sentence-transformers`, `click`, `python-dotenv`, `jieba`, `networkx`, `rank-bm25`, `pymupdf`.
