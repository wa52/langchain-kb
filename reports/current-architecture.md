# Current Call-Flow Architecture

## System Entrypoints

```
main.py
 ├── run_console()       [no args]  →  interactive TUI (prompt_toolkit)
 └── cli()               [with cmd] →  Click CLI → 1 of 14 commands
```

## Console Chat Flow (most common path)

```
user input → console.py:_get_user_input()
  │
  ├── handle_command()   [if starts with "/"]
  │     └── _do_handle_command() → dispatches to /add /ingest /rebuild /stats etc.
  │
  └── stream_rag_response(agent, msgs)   [plain text]
        │
        ├── agent streams events (deepagents)
        │     └── retrieve_knowledge tool invoked
        │           ├── _search(query, k) → get_retriever(k)
        │           │     └── get_vector_store().as_retriever(search_type="mmr")
        │           │           └── Chroma singleton (loaded from disk)
        │           │
        │           ├── _grade(query, docs, llm)  [optional]
        │           │     ├── grade_document()  → ChatOpenAI invoke
        │           │     └── (if all irrelevant) rewrite_question() → ChatOpenAI invoke
        │           │
        │           ├── _compress(docs, query, llm)  [optional]
        │           │     ├── _compress_document() → ChatOpenAI invoke per doc
        │           │     └── (or) raw truncation at MAX_CONTEXT_TOKENS * 4 chars
        │           │
        │           └── search_graph(query)  [optional]
        │                 └── KnowledgeGraph.search() → NetworkX subgraph walk
        │
        └── (after stream) compress_history()  [optional]
              └── ChatOpenAI invoke → summary of old turns
```

## Ingestion Flow

```
cli: ingest / add / rebuild / update
  │
  └── pipeline.py
        ├── run_ingestion(DATA_DIR)
        │     ├── MarkdownLoader(data_dir).load_all()
        │     │     └── _iter_files() → TextLoader / PyMuPDFLoader per file
        │     ├── create_splitter().split_documents(docs)
        │     │     └── RecursiveCharacterTextSplitter (chunk_size=500, overlap=80)
        │     ├── get_embedding_model()
        │     │     └── HuggingFaceEmbeddings (bge-small-zh-v1.5 / bge-m3 / openai)
        │     ├── get_vector_store(embeddings)
        │     │     └── Chroma(collection="langchain_docs", persist_dir)
        │     ├── add_documents_with_progress(chunks)
        │     ├── rebuild_bm25(store)
        │     │     └── BM25Retriever.from_texts() + cache as global
        │     └── build_graph_store()  [optional]
        │           └── KnowledgeGraph.build_from_chunks()
        │                 ├── [jieba mode] extract_entities + extract_relations
        │                 └── [LLM mode] ChatOpenAI batch extraction → fallback jieba
        │
        ├── run_add_path(path, external_dir)
        │     ├── shutil.copy2 → data/external/
        │     ├── load_path() → split → embed → add → rebuild_bm25 → update tracker
        │     └── build_graph_store()  [optional]
        │
        ├── run_incremental_update(internal_dir, external_dir)
        │     ├── get_changed_files() → diff tracker hashes
        │     └── delete_by_source → reload → split → embed → add → rebuild
        │
        └── run_single_file_update(filepath)
              └── delete_by_source → load → split → embed → add → rebuild
```

## Agent Loading Flow (background thread)

```
console.py:run_console()
  │
  ├── _agent_ready.clear()
  ├── threading.Thread(target=_load_agent_background, daemon=True).start()
  │     └── create_rag_agent()
  │           ├── os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"
  │           ├── get_embedding_model()          # download bge model (~33MB)
  │           ├── get_vector_store()             # open Chroma
  │           ├── rebuild_bm25(store)            # BM25 from all stored chunks
  │           ├── ChatOpenAI(model=deepseek-chat)
  │           ├── set_tool_llm(model)
  │           └── create_deep_agent(model, tools=[retrieve_knowledge, retrieve_graph])
  │
  └── main thread waits for _agent_ready Event
        ├── /help /exit /clear /sessions /mode /config /files → no agent needed
        └── everything else → blocked until _agent_ready.is_set()
```

## Key Data Flows

```
Data sources  →  MarkdownLoader / PyMuPDFLoader
                     ↓
              RecursiveCharacterTextSplitter (500/80)
                     ↓
              HuggingFaceEmbeddings  ──→  Chroma DB (langchain_docs collection)
              BM25Retriever (from Chroma texts)
                     ↓
              EnsembleRetriever [vector(0.5) + BM25(0.5)]  ──→  LLM + user
                     ↓
              KnowledgeGraph (NetworkX DiGraph) persisted to data/knowledge_graph.json
```

## Persistence Layer

| Data | Storage | Format |
|------|---------|--------|
| Vector index | `./chroma_db/` | Chroma (HNSW + SQLite) |
| File tracker | `./data/file_tracker.json` | JSON (mtime+size → md5) |
| Knowledge graph | `./data/knowledge_graph.json` | JSON (nodes + edges) |
| Chat history | `./data/chat_history/session_*.json` | JSON (messages array) |
| Config | `.env` | dotenv |
