import json
import os
import sys
from pathlib import Path

import click

from config import TOP_K


def echo_stderr(msg="", end="\n"):
    click.echo(msg, err=True, nl=(end == "\n"))


def _output(msg="", as_json=False, data=None, error=None, exit_code=None):
    if as_json:
        result = {"status": "error" if error else "ok"}
        if data is not None:
            result["data"] = data
        if error:
            result["error"] = {"code": exit_code or 1, "message": error}
        click.echo(json.dumps(result, ensure_ascii=False))
    elif msg:
        click.echo(msg)
    if exit_code:
        raise SystemExit(exit_code)


@click.group()
def kb():
    pass


@kb.command()
@click.option("--host", default="127.0.0.1", show_default=True, help="Listen address")
@click.option("--port", default=8000, type=int, show_default=True, help="Listen port")
@click.option("--reload", is_flag=True, help="Auto-reload on file change")
@click.option("--json", "as_json", is_flag=True, help="JSON output")
def serve(host, port, reload, as_json):
    """Start FastAPI + MCP service"""
    import uvicorn
    from src.api.app import app
    url = f"http://{host}:{port}"
    mcp_url = f"{url}/mcp"
    _output(f"Listening on {url}\nMCP endpoint: {mcp_url}", as_json,
            data={"url": url, "mcp": mcp_url})
    try:
        uvicorn.run(app, host=host, port=port, log_level="info")
    except OSError as e:
        _output("", as_json, error=f"Port {port} in use: {e}", exit_code=75)


@kb.command()
@click.option("--path", default=None, help="File or directory to index")
@click.option("--rebuild", is_flag=True, help="Drop collection before indexing")
@click.option("--dry-run", is_flag=True, help="Show what would be done without writing")
@click.option("--chunk-size", type=int, help="Override chunk size")
@click.option("--chunk-overlap", type=int, help="Override chunk overlap")
@click.option("--incremental", is_flag=True, help="Index only changed/new files")
@click.option("--json", "as_json", is_flag=True, help="JSON output")
def index(path, rebuild, dry_run, chunk_size, chunk_overlap, incremental, as_json):
    """Index documents into vector store"""
    from config import DATA_DIR, EXTERNAL_DIR
    from src.ingestion.pipeline import run_ingestion, run_incremental_update, run_add_path
    if rebuild and dry_run:
        _output("[dry-run] Would drop collection + re-index all files", as_json,
                data={"dry_run": True, "action": "rebuild"})
        return
    if rebuild:
        from src.vector_store.service import VectorStoreService
        echo_stderr("Dropping existing collection...")
        VectorStoreService().reset()
    kwargs = {}
    if chunk_size:
        kwargs["chunk_size"] = chunk_size
    if chunk_overlap:
        kwargs["chunk_overlap"] = chunk_overlap
    try:
        if path:
            if dry_run:
                _output(f"[dry-run] Would index: {path}", as_json,
                        data={"dry_run": True, "path": path})
                return
            count = run_add_path(path, EXTERNAL_DIR, echo_fn=echo_stderr)
        elif incremental:
            count = run_incremental_update(str(DATA_DIR), EXTERNAL_DIR, echo_fn=echo_stderr)
        else:
            count = run_ingestion(DATA_DIR, echo_fn=echo_stderr, **kwargs)
        _output(f"Indexed {count} document chunks", as_json, data={"chunks": count})
        if count == 0 and not dry_run:
            msg = f"No documents found at {path}" if path else "No documents found"
            _output("", as_json, error=msg, exit_code=3)
    except Exception as e:
        _output("", as_json, error=str(e), exit_code=1)


@kb.command()
@click.argument("query")
@click.option("--top-k", default=TOP_K, type=int, show_default=True, help="Number of results")
@click.option("--json", "as_json", is_flag=True, help="JSON output")
def search(query, top_k, as_json):
    """Search knowledge base"""
    from src.vector_store.service import VectorStoreService
    retriever = VectorStoreService().get_retriever(k=top_k)
    docs = retriever.invoke(query)
    if as_json:
        results = []
        for d in docs:
            meta = d.metadata or {}
            results.append({
                "source": meta.get("source", ""),
                "chunk_id": meta.get("chunk_id", ""),
                "score": meta.get("score", 0),
                "content": d.page_content[:500],
            })
        _output("", as_json=True, data={"results": results, "total": len(results)})
        return
    if not docs:
        click.echo("No results found.")
        return
    click.echo(f"Found {len(docs)} results:\n")
    for i, doc in enumerate(docs, 1):
        source = doc.metadata.get("source", "unknown")
        text = doc.page_content[:500]
        click.echo(f"[{i}] ({source})")
        click.echo(text)
        click.echo("")


@kb.command()
@click.argument("query", required=False)
@click.option("--session", default=None, help="Resume session ID")
@click.option("--list-sessions", "list_only", is_flag=True, help="List past sessions")
@click.option("--json", "as_json", is_flag=True, help="JSON output")
def chat(query, session, list_only, as_json):
    """Ask a RAG-powered question"""
    from src.agent.chat_history import save_history, load_history, list_sessions
    from src.agent.rag_agent import create_rag_agent, stream_rag_response

    if list_only:
        sessions = list_sessions()
        if as_json:
            _output("", as_json=True, data={"sessions": sessions})
        elif not sessions:
            click.echo("No past sessions.")
        else:
            click.echo(f"{'Session ID':<30} {'Time':<16} {'Turns':<6} Title")
            click.echo("-" * 75)
            for s in sessions:
                title = s.get("title", "")
                click.echo(f"{s['id']:<30} {s['created']:<16} {s['turns']:<6} {title}")
        return

    if not query:
        _output("", as_json, error="QUERY argument is required", exit_code=2)

    raw_history = []
    if session:
        saved = load_history(session)
        if saved is None:
            _output("", as_json, error=f"Session not found: {session}", exit_code=3)
        raw_history = saved

    messages = raw_history + [{"role": "user", "content": query}]
    agent = create_rag_agent()
    answer_parts = []
    if as_json:
        for chunk in stream_rag_response(agent, messages):
            if chunk:
                answer_parts.append(chunk)
        full = "".join(answer_parts)
        new_msgs = [{"role": "user", "content": query},
                    {"role": "assistant", "content": full}]
        sid = save_history(raw_history + new_msgs, session)
        _output("", as_json=True, data={"answer": full, "session_id": sid})
    else:
        for chunk in stream_rag_response(agent, messages):
            if chunk:
                click.echo(chunk, nl=False)
                answer_parts.append(chunk)
        click.echo()
        full = "".join(answer_parts)
        new_msgs = [{"role": "user", "content": query},
                    {"role": "assistant", "content": full}]
        save_history(raw_history + new_msgs, session)


@kb.command()
@click.option("--json", "as_json", is_flag=True, help="JSON output")
def status(as_json):
    """Show knowledge base status"""
    from src.vector_store.service import VectorStoreService
    from src.graph_store.service import GraphService

    try:
        vs_stats = VectorStoreService().get_stats()
    except Exception as e:
        vs_stats = {"error": str(e)}
    try:
        gs_stats = GraphService().get_stats()
    except Exception:
        gs_stats = {"entities": 0, "relations": 0}

    if as_json:
        _output("", as_json=True, data={
            "vector_store": vs_stats,
            "graph": gs_stats,
        })
    else:
        vs = vs_stats.get("count", vs_stats.get("error", "?"))
        vs_src = vs_stats.get("source_count", "?")
        ge = gs_stats.get("entities", 0)
        gr = gs_stats.get("relations", 0)
        click.echo(f"Vector Store:     {vs} chunks, {vs_src} sources")
        click.echo(f"Knowledge Graph:  {ge} entities, {gr} relations")


@kb.command()
@click.option("--verbose", is_flag=True, help="Show detailed diagnostics")
@click.option("--json", "as_json", is_flag=True, help="JSON output")
def doctor(verbose, as_json):
    """Diagnose configuration, model, vector store, dependencies"""
    checks = []

    def add(name, passed, detail="", fix_hint=""):
        checks.append({"name": name, "passed": passed, "detail": detail, "fix": fix_hint})

    add("Config file", Path(".env").exists() or Path("../.env").exists())
    api_key = os.getenv("DEEPSEEK_API_KEY", "")
    add("DEEPSEEK_API_KEY", bool(api_key))

    try:
        from src.vector_store.embedding import get_embedding_model
        m = get_embedding_model()
        label = getattr(m, "model_name", "loaded") if m else "none"
        add("Embedding model", True, detail=str(label))
    except Exception as e:
        add("Embedding model", False, detail=str(e), fix_hint="Check network / HF_ENDPOINT")

    try:
        from src.vector_store.chroma_client import get_vector_store
        s = get_vector_store()
        add("Vector store", s is not None)
    except Exception as e:
        add("Vector store", False, detail=str(e), fix_hint="Run: kb index")

    try:
        from src.graph_store.service import GraphService
        ec = GraphService().get_entity_count()
        add("Knowledge graph", True, detail=f"{ec} entities")
    except Exception as e:
        add("Knowledge graph", False, detail=str(e))

    try:
        from src.llm import get_llm
        llm = get_llm(temperature=0)
        llm.invoke("hi")
        add("LLM API", True, detail="responds")
    except Exception as e:
        add("LLM API", False, detail=str(e), fix_hint="Check DEEPSEEK_API_KEY")

    for pkg in ["sentence_transformers", "chromadb", "click", "fastapi", "uvicorn",
                 "jieba", "networkx"]:
        _name = f"Package: {pkg}"
        try:
            __import__(pkg)
            add(_name, True)
        except ImportError:
            add(_name, False, fix_hint=f"pip install {pkg}")

    passed = sum(1 for c in checks if c["passed"])
    total = len(checks)
    fixes = [c["fix"] for c in checks if not c["passed"] and c.get("fix")]

    if as_json:
        _output("", as_json=True, data={
            "checks": checks, "passed": passed, "total": total, "fixes": fixes,
        })
        return

    for c in checks:
        icon = "[OK]" if c["passed"] else "[FAIL]"
        detail = f"  ({c['detail']})" if c.get("detail") else ""
        click.echo(f"{icon} {c['name']}{detail}")
        if verbose and not c["passed"] and c.get("fix"):
            click.echo(f"   Fix: {c['fix']}")

    click.echo(f"\nSummary: {passed}/{total} checks passed")
    if fixes:
        click.echo("Issues found:")
        for f in fixes:
            click.echo(f"  Run: {f}")

    if passed < total:
        _output("", as_json, error=f"{total - passed} check(s) failed", exit_code=1)

    if as_json:
        return
    if passed < total:
        raise SystemExit(1)


@kb.command()
@click.option("--key", default=None, help="Show a single config key")
@click.option("--validate", is_flag=True, help="Validate current config")
@click.option("--json", "as_json", is_flag=True, help="JSON output")
def config(key, validate, as_json):
    """View or validate configuration"""
    from config import (
        DATA_DIR, EXTERNAL_DIR, CHUNK_SIZE, CHUNK_OVERLAP, TOP_K,
        EMBEDDING_MODEL, LLM_MODEL,
        ENABLE_GRADING, ENABLE_REWRITE, ENABLE_HYBRID_SEARCH,
        ENABLE_CONTEXT_COMPRESSION, ENABLE_GRAPH, ENABLE_GRAPH_LLM_EXTRACTION,
        MAX_CONTEXT_TOKENS,
    )
    keys = [
        ("DATA_DIR", str(DATA_DIR)),
        ("EXTERNAL_DIR", EXTERNAL_DIR),
        ("EMBEDDING_MODEL", EMBEDDING_MODEL),
        ("LLM_MODEL", LLM_MODEL),
        ("CHUNK_SIZE", str(CHUNK_SIZE)),
        ("CHUNK_OVERLAP", str(CHUNK_OVERLAP)),
        ("TOP_K", str(TOP_K)),
        ("MAX_CONTEXT_TOKENS", str(MAX_CONTEXT_TOKENS)),
        ("ENABLE_GRADING", str(ENABLE_GRADING)),
        ("ENABLE_REWRITE", str(ENABLE_REWRITE)),
        ("ENABLE_HYBRID_SEARCH", str(ENABLE_HYBRID_SEARCH)),
        ("ENABLE_CONTEXT_COMPRESSION", str(ENABLE_CONTEXT_COMPRESSION)),
        ("ENABLE_GRAPH", str(ENABLE_GRAPH)),
        ("ENABLE_GRAPH_LLM_EXTRACTION", str(ENABLE_GRAPH_LLM_EXTRACTION)),
    ]

    if key:
        matches = [(k, v) for k, v in keys if k == key]
        if not matches:
            _output("", as_json, error=f"Unknown key: {key}", exit_code=3)
        k, v = matches[0]
        if as_json:
            _output("", as_json=True, data={"key": k, "value": v})
        else:
            click.echo(f"{k}={v}")
        return

    if validate:
        issues = []
        if not Path(DATA_DIR).exists():
            issues.append("DATA_DIR does not exist")
        if not os.getenv("DEEPSEEK_API_KEY"):
            issues.append("DEEPSEEK_API_KEY is not set")
        if CHUNK_SIZE < 100 or CHUNK_SIZE > 2000:
            issues.append(f"CHUNK_SIZE={CHUNK_SIZE} outside valid range 100–2000")
        if TOP_K < 1 or TOP_K > 50:
            issues.append(f"TOP_K={TOP_K} outside valid range 1–50")

        if as_json:
            _output("", as_json=True, data={"valid": len(issues) == 0, "issues": issues})
        elif issues:
            click.echo("Configuration issues:")
            for i in issues:
                click.echo(f"  ✖ {i}")
        else:
            click.echo("✔ All checks passed — configuration is valid")
        return

    if as_json:
        data = [{"key": k, "value": v} for k, v in keys]
        _output("", as_json=True, data={"keys": data})
    else:
        click.echo(f"{'Key':<35} {'Value':<30}")
        click.echo("-" * 66)
        for k, v in keys:
            click.echo(f"{k:<35} {v:<30}")


if __name__ == "__main__":
    kb()
