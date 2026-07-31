# AGENTS.md — LangChain RAG 知识库系统

## Quick start

```powershell
pip install -r requirements.txt
python main.py ingest          # 1st: build vector index
python main.py                 # interactive console with status bar + 14 slash commands
python main.py search <query>  # vector search only
```

Global command (usable from any directory, after `pip install -e .`):

```powershell
knowledge web        # start Web UI + API + MCP (--open opens browser)
knowledge cli        # interactive console
knowledge search "q" # vector search
```

Data locations are anchored to `KNOWLEDGE_HOME` (defaults to project root) — see `docs/global-usage.md`. Relative `CHROMA_PERSIST_DIR`/`EXTERNAL_DIR`/`GRAPH_PERSIST_DIR`/`DATA_DIR` resolve against it, so commands work from any cwd.

## Entrypoints

| Entry | Trigger | What loads |
|-------|---------|------------|
 | `python main.py` (no args) | `run_console()` in `console.py` | interface appears immediately; agent loads in background |
| `python main.py <cmd>` | Click CLI (14 commands) in `commands.py` | depends on cmd |

## Console slash commands (`/help` lists all 14)

| Command | Action |
|---------|--------|
| `/add <path>` | Copy file/dir to `data/external/`, index, show `[0%→100%]` progress bar |
| `/remove <name>` | Remove file from knowledge base |
| `/ingest` | Full re-import from DATA_DIR |
| `/rebuild` | Drop collection + re-import (asks confirm) |
| `/mode [llm\|jieba]` | Toggle graph extraction backend (persisted to `.env`) |
| `/new` `/resume <id>` `/sessions` | Chat session management |
| `/stats` `/config` `/files` `/clear` `/exit` | Info & utility |

## Architecture

```
main.py
  ├─ src/cli/
  │    commands.py   — Click CLI (14 commands) + echo() helper
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
python -m pytest tests/         # 65 tests (~30s)
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
- **Console** (`console.py`) also passes `echo_fn=echo` — console's own `echo()` that first tries `prompt_toolkit.print_formatted_text`, with `\r` detection that writes directly to `sys.stdout` (bypasses pt_print), and falls through to the CLI `echo()` on error.
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

6. **`handle_command` wraps inner logic** — exceptions from `/add`/`/remove`/etc. are caught by an outer wrapper in `handle_command()` (`console.py:138-144`) that prints traceback and returns an error string. The inner `_do_handle_command()` has no per-command try/except.

7. **`echo("助手: ", end="")` (console.py:386)** — only works because `echo()` now accepts `end` param. Before the change it was a latent bug.

8. **Background agent loading** — `console.py` loads `create_rag_agent()` in a daemon thread so the interface appears immediately. The background thread owns the only httpx session (no sharing with main thread), so it avoids the thread-pool conflict from gotcha #3. During loading, `_agent_ready` Event blocks agent-dependent commands with "正在加载" message.

9. **`\r` in console echo** — console's `echo()` detects `\r` in the message and writes directly to `sys.stdout` (bypassing `prompt_toolkit.print_formatted_text`). This prevents OOM from accumulated progress bar lines during long `/add` operations. Fallback path still catches `UnicodeEncodeError` for GBK safety.

10. **tqdm suppression** — `HF_HUB_DISABLE_PROGRESS_BARS=1` set at the start of `create_rag_agent()` to suppress raw progress bar output from `sentence_transformers`/`huggingface_hub` during model loading.

11. **ChromaDB + non-ASCII path** — chromadb's Rust bindings fail to open a persist dir whose path contains non-ASCII (Chinese) characters: `InternalError: os error 123`. Keep `CHROMA_PERSIST_DIR` on an ASCII-only path (e.g. `C:\Users\<user>\.knowledge\chroma_db`). This repo's own folder name contains Chinese, so the default `./chroma_db` resolves under a Chinese path and is unusable — set `CHROMA_PERSIST_DIR` in `.env`.

## Config (.env)

| Key | Default | Description |
|-----|---------|-------------|
| `DATA_DIR` | `./data/docs` | Source document directory (auto-created) |
| `EXTERNAL_DIR` | `./data/external` | External files copied via `/add` |
| `CHROMA_PERSIST_DIR` | `./chroma_db` | Vector store persistence |
| `EMBEDDING_MODEL` | `bge-small-zh` | `bge-m3`, `bge-small-zh`, `bge-base-zh`, or `openai` |
| `LLM_MODEL` | `deepseek-chat` | Model name for ChatOpenAI |
| `DEEPSEEK_API_KEY` | (set in .env) | DeepSeek / OpenAI-compatible API key |
| `DEEPSEEK_API_BASE` | `https://api.deepseek.com` | API base URL |
| `CHUNK_SIZE` / `CHUNK_OVERLAP` | `500` / `80` | Document chunking |
| `TOP_K` | `5` | Retrieval count |
| `ENABLE_GRAPH` | `true` | Enable knowledge graph |
| `ENABLE_GRAPH_LLM_EXTRACTION` | `false` | Use DeepSeek (instead of jieba) for graph extraction |
| `ENABLE_CONTEXT_COMPRESSION` | `true` | Compress chat history via LLM summary (keeps last 10 rounds) |
| `ENABLE_HYBRID_SEARCH` | `true` | BM25 + vector ensemble retrieval |
| `ENABLE_GRADING` / `ENABLE_REWRITE` | `true` / `true` | Relevance grading / query rewrite |
| `GRAPH_LLM_BATCH_SIZE` | `10` | Batch size for LLM extraction |
| `MAX_CONTEXT_TOKENS` | `1000` | Max tokens per retrieved doc |

## Change model

```powershell
# .env: EMBEDDING_MODEL=bge-m3 → python main.py rebuild
```

## Dependencies

Key: `deepagents`, `langchain`, `langchain-chroma`, `langchain-huggingface`, `langchain-openai`, `prompt_toolkit`, `chromadb`, `sentence-transformers`, `click`, `python-dotenv`, `jieba`, `networkx`, `rank-bm25`, `pymupdf`.

## knowledge-service MCP

OpenCode 通过 `knowledge-service` MCP 连接本地知识库 API（端口 8000，Streamable HTTP 传输）。

### 使用规则

1. **涉及内部文档、项目经验、错误记录、架构规范时，优先调用 knowledge-service**。这是获取项目自有知识的第一手段。
2. **需要原始证据时使用 `search_knowledge`** — 返回文档片段、来源路径和相关性分数。适合查证事实、寻找关键段落、追溯信息来源。
3. **需要直接答案时使用 `answer_with_knowledge`** — RAG 增强的对话式回答，附带引用来源。适合总结、解释概念、多轮问答。
4. **查询索引任务时使用 `get_index_status`** — 检查异步索引任务的进度和结果。
5. **不得伪造知识库未返回的来源** — 如果知识库没有相关信息，必须如实说明，不得编造引用或来源。
6. **查询无结果时必须明确说明** — 不要在无依据的情况下推断或杜撰答案。

### 启用方式

```powershell
# 终端 1：启动 API 服务
python main.py api

# 终端 2：验证 MCP 连接
opencode mcp list
# → ✓ knowledge-service connected
```
