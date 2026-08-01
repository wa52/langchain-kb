# Agent Notes

## Commands

```powershell
pip install -r requirements.txt
python -m pytest tests/                 # full suite
python -m pytest tests/test_console.py -v  # focused suite
python main.py ingest                   # legacy Click CLI: full import
python main.py                           # interactive console
python main.py api                       # FastAPI + Web UI/MCP on port 8000
pip install -e .                         # installs the `knowledge` command
knowledge --help
```

The installed Typer CLI is the preferred user-facing interface: `knowledge web`,
`knowledge cli`, `knowledge search "query"`, `knowledge chat "query"`,
`knowledge index <path>`, `knowledge status`, `knowledge doctor`, and
`knowledge serve`. The older Click commands remain available through `main.py`.

There is no configured lint, formatter, typecheck, or code-generation command; use
the focused pytest target while changing a subsystem, then run the full suite.

## Layout

- `main.py` dispatches the legacy CLI, console, API server, and `main.py knowledge`.
- `src/cli/knowledge.py` is the installed `knowledge` CLI; `src/api/` owns FastAPI/Web/MCP.
- `src/ingestion/` loads and splits documents; `src/vector_store/` owns Chroma and embeddings.
- `src/retrieval/` implements hybrid vector/BM25 retrieval; `src/graph_store/` persists the NetworkX graph.
- `src/agent/` builds the Deep Agent and persists chat sessions; `tests/` contains the behavioral test suite.

## Runtime Constraints

- Python `>=3.10`; dependencies are defined in `requirements.txt` and exposed by `pyproject.toml`.
- Set `KNOWLEDGE_HOME` as an environment variable before starting a process when using a relocated data directory. It selects the `.env`; relative `DATA_DIR`, `EXTERNAL_DIR`, `CHROMA_PERSIST_DIR`, and `GRAPH_PERSIST_DIR` resolve under it.
- ChromaDB cannot reliably open a persistence path containing non-ASCII characters on Windows. Set `CHROMA_PERSIST_DIR` to an ASCII-only absolute path when the repository path contains Chinese characters.
- `DEEPSEEK_API_KEY` is required for LLM chat and LLM graph extraction, but most tests mock external services and do not need it.
- `HF_ENDPOINT` must be set before Hugging Face imports. `hf-mirror.com` now 308-redirects model files to `huggingface.co` and `huggingface_hub` rejects that redirect (`FileMetadataError`), so this repo's `.env` ships `HF_ENDPOINT=https://huggingface.co`. Use that whenever a proxy can reach the official site; pre-warm the cache once via `hf download BAAI/bge-small-zh-v1.5` (~33 MB) so startup does not depend on the network. Model-loading tests can take about 15 seconds and may download the embedding model.
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
