# Agent Notes

## Commands

```powershell
kb_env\Scripts\pip install -r requirements.txt   # install runtime deps into the dev venv
python -m pytest tests/                 # full suite (uses GLOBAL Python 3.13, not kb_env)
python -m pytest tests/test_console.py -v  # focused suite
kb_env\Scripts\python.exe -m uvicorn src.api.app:app --host 127.0.0.1 --port 8000  # run API server from the dev venv
python main.py ingest                   # legacy Click CLI: full import
python main.py                           # interactive console
python main.py api                       # FastAPI + Web UI/MCP on port 8000
pip install -e .                         # installs the `knowledge` command
knowledge --help
```

## Web client (`web/`)

- `web/` is an independent Vite + React + TypeScript app; its build output `web/dist/` is served by FastAPI (user still runs one service).
- Build: `cd web; npm install; npm run build` (typecheck: `npm run typecheck`; dev: `npm run dev`, which proxies `/api` to 127.0.0.1:8000).
- `web/dist` and `web/node_modules` are gitignored; the embedded single-file UI (`src/api/web.py`) remains the fallback when no build exists.
- Streaming chat: `POST /api/v1/chat/stream` emits SSE events `message_start / token / sources / message_end / error`; interrupted runs are saved to history with `interrupted=true`.

- Two Python environments coexist: the dev venv `kb_env/` (Python 3.13; holds all runtime deps and is what the running API service uses) and the global `python` (Python 3.13; has pytest). Run tests with `python -m pytest` — **pytest is not installed in `kb_env`** (`kb_env\Scripts\python -m pytest` fails).
- The installed Typer CLI is the preferred user-facing interface: `knowledge web`, `knowledge cli`, `knowledge search "query"`, `knowledge chat "query"`, `knowledge index <path>`, `knowledge status`, `knowledge doctor`, and `knowledge serve`. The older Click commands remain available through `main.py`. Project self-check is a standalone program: `python selfcheck.py` (read-only) or `python selfcheck.py --repair` (probe components and auto-repair); its engine lives in `src/monitor.py` (`python -m src.monitor`).
- There is no configured lint, formatter, typecheck, or code-generation command; use the focused pytest target while changing a subsystem, then run the full suite.

## Layout

- `main.py` dispatches the legacy CLI, console, API server, and `main.py knowledge`.
- `src/cli/knowledge.py` is the installed `knowledge` CLI; `src/api/` owns FastAPI/Web/MCP.
- `src/ingestion/` loads and splits documents; `src/vector_store/` owns Chroma and embeddings.
- `src/retrieval/` implements hybrid vector/BM25 retrieval; `src/graph_store/` persists the NetworkX graph.
- `src/agent/` builds the Deep Agent and persists chat sessions; `tests/` contains the behavioral test suite.

## Runtime Constraints

- Python `>=3.10`; dependencies are defined in `requirements.txt` and exposed by `pyproject.toml`.
- Set `KNOWLEDGE_HOME` as an environment variable before starting a process when using a relocated data directory. It selects the `.env`; relative `DATA_DIR`, `EXTERNAL_DIR`, `CHROMA_PERSIST_DIR`, `GRAPH_PERSIST_DIR`, `CHAT_HISTORY_DIR` (`data/chat_history`), and `FILE_TRACKER_PATH` (`data/file_tracker.json`) resolve under it. The latter two have env overrides and must not be bare CWD-relative paths.
- ChromaDB cannot reliably open a persistence path containing non-ASCII characters on Windows. Set `CHROMA_PERSIST_DIR` to an ASCII-only absolute path when the repository path contains Chinese characters.
- `DEEPSEEK_API_KEY` is required for LLM chat and LLM graph extraction, but most tests mock external services and do not need it.
- `huggingface.co` is **unreachable from this machine** (WinError 10060 / connection timeout). Without offline mode the HF client retries every model file 5x with backoff, so API startup looks hung for several minutes. Set `HF_HUB_OFFLINE=1` before starting the server (bge-small-zh-v1.5 is already cached locally; startup then completes in ~40s). Keep `.env`'s `HF_ENDPOINT=https://huggingface.co`; `hf download` cannot pre-warm the cache here because the network is down.
- API server startup runs 5 steps (`[1/5]` embedding model → `[2/5]` LLM client → `[3/5]` Chroma → `[4/5]` knowledge graph → `[5/5]` BM25 index). Confirm readiness with `GET http://127.0.0.1:8000/api/v1/health` (HTTP 200), not by checking the listening port.
- `create_rag_agent()` deliberately initializes the embedding model and Chroma store before creating the agent. Preserve this order; the Hugging Face/httpx client is unsafe when initialized from the wrong thread.
- Hybrid retrieval uses `EnsembleRetriever` from `langchain_classic`, and its BM25 index must be rebuilt after data changes.
- Windows terminals may use GBK. Keep progress output ASCII (`#`, `.`, `\r`) and preserve the UTF-8/replace stdout wrappers; do not use `rich.console.Markdown` for terminal output.

## Data And Configuration

- `.env.example` is the safe template; do not expose `.env` or API keys in changes.
- Startup calls `ensure_data_dirs()`, creating the configured docs, external-data, and Chroma directories.
- `data/external/` is the destination for files added through `/add` or `knowledge index`; the file tracker enables incremental updates.
- Changing `EMBEDDING_MODEL` requires rebuilding the index (`python main.py rebuild` or the corresponding `knowledge index --rebuild` flow).
- The interactive console loads the agent in a daemon background thread and blocks agent-dependent commands until loading completes.

## Console Behavior

- `/help` is the source of truth for console commands: `/new`, `/sessions`, `/resume`, `/add`, `/files`, `/remove`, `/mode`, `/ingest`, `/rebuild`, `/stats`, `/config`, `/clear`, `/exit`.
- Pipeline and progress functions accept `echo_fn`; pass the caller's output function instead of hard-coding `print`, especially in CLI/console code and tests.
- `/mode llm` and `/mode jieba` persist `ENABLE_GRAPH_LLM_EXTRACTION` to `.env`; LLM mode consumes the DeepSeek API.
