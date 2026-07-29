# AGENTS.md — LangChain RAG 知识库系统

## Quick start

```powershell
cd D:\langchain数据库
pip install -r requirements.txt
python main.py ingest       # 1st: build vector index
python main.py chat         # interactive Q&A
```

## Quick start (BAT launcher)

```powershell
cd D:\langchain数据库
chat.bat              # 进入交互式问答 (python main.py chat)
chat.bat search xxx   # 搜索知识库
chat.bat stats        # 查看知识库统计
chat.bat config       # 查看配置
```

## CLI commands (`python main.py <command>`)

| Command | Action |
|---------|--------|
| `ingest` | Full import: load .md/.txt/.pdf → split → embed → ChromaDB |
| `update` | Incremental: only process files with changed mtime/size |
| `update-file <path>` | Re-index a single file |
| `rebuild` | Drop collection + full re-import |
| `search <query>` | Vector search only (no LLM) |
| `chat [--session <id>] [--list-sessions]` | Multi-turn Q&A with history persistence |
| `stats` | Show detailed knowledge base statistics |
| `add <path>` | Copy external file/dir into `data/external/` and index |
| `list-files` | List all tracked files in knowledge base |
| `remove <name>` | Remove a file from vector store + disk + tracker |
| `config` | Show current settings |
| `build-graph` | Build knowledge graph from all documents |
| `graph-search <query>` | Search knowledge graph |

## Architecture

```
main.py → Click CLI → src/cli/commands.py
  ├─ src/ingestion/      loader.py | splitter.py | pipeline.py | tracker.py
  ├─ src/vector_store/   chroma_client.py | embedding.py
  ├─ src/retrieval/      retriever.py | grading.py | rewrite.py
  ├─ src/graph_store/    graph.py | extraction.py | retriever.py
  └─ src/agent/          tools.py | rag_agent.py | chat_history.py
```

- **Agent harness:** `deepagents` (`create_deep_agent`) with one `@tool` — `retrieve_knowledge`
- **Vector store:** ChromaDB, collection `langchain_docs`, persisted to `./chroma_db/`
- **Embedding:** `BAAI/bge-small-zh-v1.5` (free, offline, 384-dim), cached via `@lru_cache`
- **LLM:** `deepseek-chat` via `ChatOpenAI(openai_compatible)` at `https://api.deepseek.com`
- **Data:** referenced directly from `C:\Users\SJ\Desktop\md\langchain_data` (~81 source files, 1879 chunks)
- **Chat history:** saved as JSON in `./data/chat_history/`, restorable via `--session <id>`
- **Supported file types:** `.md`, `.txt`, `.pdf`

## Critical gotchas

1. **GBK terminal crash** — Windows PowerShell with `chs` codepage cannot render Rich/emoji/Unicode. `main.py` wraps stdout with `utf-8/replace`. Never use `rich.console` Markdown rendering; use `print()` with `.encode('gbk', errors='replace')` fallback. See `src/cli/commands.py:echo()`.

2. **HuggingFace mirror required** — `HF_ENDPOINT=https://hf-mirror.com` must be set **before** any `huggingface_hub` import. Set in `config.py:17-19` and `embedding.py:5-7` at module level. The model weights are ~2.2GB (bge-m3) or ~33MB (bge-small-zh); first download uses the mirror.

3. **Embedding model must be pre-loaded** — `huggingface_hub` uses a shared `httpx` client that breaks in thread pools. Deep Agents runs `@tool` calls in a thread executor. **Always call `get_embedding_model()` + `get_vector_store()` in the main thread before creating the agent.** Already handled in `rag_agent.py:23-24`.

4. **DeepSeek uses OpenAI-compatible API** — model string is `deepseek-chat`, but the client is `ChatOpenAI` with `base_url=https://api.deepseek.com`. Never use a native DeepSeek SDK.

5. **File tracker for incremental updates** — stored at `./data/file_tracker.json`. Tracks `md5(mtime + size)` per file. A clean clone or rebuild requires running `ingest` or `rebuild` to populate the tracker.

6. **BM25 hybrid search** — `EnsembleRetriever` must be imported from `langchain_classic.retrievers.ensemble` (not `langchain.retrievers`, which doesn't exist in langchain 1.3.x). Handled in `src/retrieval/retriever.py`. BM25 index is rebuilt after every data change via `_rebuild_bm25()`.

7. **Text splitter** — `RecursiveCharacterTextSplitter` with custom separators prioritizing markdown structure: `["\n## ", "\n### ", "\n```\n", "\n\n", "\n", "。", ".", " ", ""]`. `keep_separator=False`.

8. **Knowledge graph** — Built via `build-graph` command or automatically after `ingest`/`update`/`add`. Uses `jieba` for Chinese word segmentation + `networkx` for in-memory graph. Persisted to `./data/knowledge_graph.json`. Min entity frequency is 3 to reduce noise. The Agent gets two tools: `retrieve_knowledge` (vector) and `retrieve_graph` (graph).

## Embedding model switching

## Embedding model switching

Edit `.env`: `EMBEDDING_MODEL=bge-m3` (multilingual, 8192 tokens, ~2.2GB) or `bge-small-zh` (Chinese-optimized, 512 tokens, ~33MB). Then run `python main.py rebuild`.

## Config (.env keys)

| Key | Default | Description |
|-----|---------|-------------|
| `ENABLE_GRAPH_LLM_EXTRACTION` | `false` | Use DeepSeek instead of jieba for entity extraction |
| `GRAPH_LLM_BATCH_SIZE` | `10` | Chunks per batch when calling LLM |

## Dependencies

Key packages: `deepagents`, `langchain`, `langchain-chroma`, `langchain-huggingface`, `langchain-openai`, `chromadb`, `sentence-transformers`, `click`, `python-dotenv`, `jieba`, `networkx`.
