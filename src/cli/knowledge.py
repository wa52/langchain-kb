import contextlib
import io
import json
import os
import re
import socket
import sys
from pathlib import Path
from typing import Literal

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.progress import BarColumn, Progress, TextColumn
from rich.table import Table

from config import PRODUCT_NAME

app = typer.Typer(
    add_completion=False,
    no_args_is_help=False,
    invoke_without_command=True,
    context_settings={"help_option_names": ["-h", "--help"]},
    help=f"{PRODUCT_NAME}命令行工具",
    epilog=(
        "示例:\n"
        "  knowledge index ./docs\n"
        '  knowledge search "什么是RAG?"\n'
        "  knowledge serve --port 8000"
    ),
)

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_NOT_FOUND = 3
EXIT_TRANSIENT = 75
EXIT_CONFIG = 78

_COLOR_MODE = "auto"

_SOURCE_RE = re.compile(r"\[来源:\s*([^\]]+)\]")
_STAGE_RE = re.compile(r"^\[([\d.]+/\d+)\]\s*(.*)$")
_PCT_RE = re.compile(r"^\[\s*(\d+)%\]")


def _resolve_color(stream) -> bool:
    """Apply the color evaluation order: FORCE_COLOR > --color > NO_COLOR
    > TERM=dumb > TTY detection."""
    if os.environ.get("FORCE_COLOR"):
        return True
    if _COLOR_MODE == "always":
        return True
    if _COLOR_MODE == "never":
        return False
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("TERM") == "dumb":
        return False
    return stream.isatty()


def _console(file):
    if _resolve_color(file):
        return Console(highlight=False, file=file, color_system="standard", no_color=False)
    return Console(highlight=False, file=file, no_color=True)


def _data_console() -> Console:
    return _console(sys.stdout)


def _err_console() -> Console:
    return _console(sys.stderr)


def _emit_json(payload: dict):
    print(json.dumps(payload, ensure_ascii=False))


def _json_error(code, message, type_, recoverable, suggestions=()):
    print(json.dumps({
        "status": "error",
        "error": {
            "code": code,
            "type": type_,
            "message": message,
            "recoverable": recoverable,
            "suggestions": list(suggestions),
        },
    }, ensure_ascii=False), file=sys.stderr)


def _fail(as_json, exit_code, message, code, type_, recoverable, suggestions=()):
    if as_json:
        _json_error(code, message, type_, recoverable, suggestions)
    else:
        _err_console().print(f"[red]{message}[/red]")
    _exit(exit_code)


def _exit(code: int):
    raise typer.Exit(code)


_COMMANDS = [
    ("serve", "启动 API + MCP 服务"),
    ("index", "索引文件或目录到向量库"),
    ("search", "检索知识片段"),
    ("chat", "基于知识库回答"),
    ("status", "查看系统状态"),
    ("doctor", "健康检查"),
]


def _print_concise_help():
    typer.echo(f"{PRODUCT_NAME}命令行工具")
    typer.echo()
    typer.echo("用法: knowledge [命令] [选项]")
    typer.echo()
    typer.echo("示例:")
    typer.echo("  knowledge index ./docs")
    typer.echo('  knowledge search "什么是RAG?"')
    typer.echo("  knowledge serve --port 8000")
    typer.echo()
    typer.echo("常用命令:")
    for name, desc in _COMMANDS:
        typer.echo(f"  {name:<8}{desc}")
    typer.echo()
    typer.echo("使用 knowledge --help 查看完整帮助")


@app.callback()
def main(
    ctx: typer.Context,
    color: Literal["always", "auto", "never"] = typer.Option(
        "auto", "--color", help="颜色输出: always / auto / never"),
    no_color: bool = typer.Option(False, "--no-color", help="禁用颜色（等价于 --color=never）"),
):
    global _COLOR_MODE
    if no_color:
        color = "never"
    _COLOR_MODE = color
    if ctx.invoked_subcommand is None:
        _print_concise_help()


def _port_open(port: int = 8000, host: str = "127.0.0.1") -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.5):
            return True
    except OSError:
        return False


class _PipelineEcho:
    """Routes ingestion pipeline echo_fn into a Rich progress bar (stderr).

    Parses `[N/M] stage` headers and `[ NN%]` progress lines emitted by the
    existing pipeline services; info lines print to stderr. Disabled entirely
    when as_json=True so stdout stays pure JSON.
    """

    def __init__(self, console: Console, enabled: bool = True):
        self.console = console
        self.enabled = enabled
        self._progress = None
        self._task_id = None
        if enabled and console.is_terminal:
            self._progress = Progress(
                TextColumn("[bold cyan]{task.description}"),
                BarColumn(),
                TextColumn("{task.percentage:>3.0f}%"),
                console=console,
            )
            self._progress.start()

    def __call__(self, msg="", end="\n"):
        if not self.enabled:
            return
        text = str(msg).strip()
        if not text:
            return
        m = _PCT_RE.match(text)
        if m and self._progress is not None and self._task_id is not None:
            self._progress.update(self._task_id, completed=int(m.group(1)))
            return
        m = _STAGE_RE.match(text)
        if m:
            label = m.group(2).rstrip(" .")
            if self._progress is not None:
                if self._task_id is None:
                    self._task_id = self._progress.add_task(label, total=100)
                else:
                    self._progress.update(self._task_id, description=label, completed=0)
            return
        self.console.print(text)

    def finish(self):
        if self._progress is not None:
            self._progress.stop()


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", help="监听地址"),
    port: int = typer.Option(8000, help="监听端口"),
    reload: bool = typer.Option(False, help="开发模式自动重载"),
    as_json: bool = typer.Option(False, "--json", help="JSON 输出"),
):
    """启动 API + MCP 服务"""
    import uvicorn

    from src.api.app import create_app

    url = f"http://{host}:{port}"
    if as_json:
        _emit_json({"status": "ok", "data": {
            "url": url,
            "web": f"{url}/",
            "swagger": f"{url}/docs",
            "mcp": f"{url}/mcp",
        }})
    else:
        panel = Panel(
            f"[bold]Web:[/bold] {url}/\n"
            f"[bold]API 文档:[/bold] {url}/docs\n"
            f"[bold]MCP:[/bold] {url}/mcp",
            title=f"{PRODUCT_NAME}服务",
            border_style="cyan",
        )
        _data_console().print(panel)
    try:
        app_obj = create_app()
        uvicorn.run(app_obj, host=host, port=port, reload=reload, log_level="info")
    except OSError as e:
        _fail(
            as_json, EXIT_TRANSIENT,
            f"端口 {port} 被占用: {e}",
            "PORT_BUSY", "port_busy", recoverable=True,
            suggestions=[
                f"换一个端口: knowledge serve --port {port + 1}",
                f"检查占用进程: netstat -ano | findstr :{port}",
            ],
        )


@app.command()
def index(
    path: str = typer.Argument(..., help="要索引的文件或目录路径"),
    incremental: bool = typer.Option(False, help="增量模式（仅处理变更文件）"),
    force: bool = typer.Option(False, help="强制重建（删除旧索引后重新索引）"),
    as_json: bool = typer.Option(False, "--json", help="JSON 输出"),
):
    """索引文件或目录到向量库"""
    from config import DATA_DIR, EXTERNAL_DIR
    from src.ingestion.pipeline import (
        run_add_path, run_incremental_update, run_single_file_update,
    )
    from src.ingestion.tracker import get_changed_files
    from src.vector_store.chroma_client import delete_by_source

    target = Path(path)
    if not target.exists():
        _fail(
            as_json, EXIT_NOT_FOUND,
            f"路径不存在: {path}",
            "NOT_FOUND", "path_not_found", recoverable=False,
            suggestions=[
                "检查路径拼写后重试: knowledge index <path>",
                "使用绝对路径或相对路径",
            ],
        )

    echo = _PipelineEcho(_err_console(), enabled=not as_json)
    processed = 0
    skipped = 0
    failed = 0
    error = None
    with contextlib.redirect_stdout(io.StringIO()) if as_json else contextlib.nullcontext():
        try:
            if incremental:
                changed, unchanged = get_changed_files([
                    (str(DATA_DIR), "internal"),
                    (str(EXTERNAL_DIR), "external"),
                ])
                processed = len(changed)
                skipped = len(unchanged)
                if changed:
                    run_incremental_update(str(DATA_DIR), str(EXTERNAL_DIR), echo_fn=echo)
            elif target.is_dir():
                processed = run_add_path(str(target), str(EXTERNAL_DIR), echo_fn=echo)
            else:
                if force:
                    delete_by_source(target.name)
                processed = run_single_file_update(str(target), echo_fn=echo)
        except Exception as e:
            error = e
    echo.finish()

    if error is not None:
        failed = 1
        _fail(
            as_json, EXIT_ERROR,
            f"索引失败: {error}",
            "INDEX_FAILED", "index_failed", recoverable=True,
            suggestions=[
                f"修复问题后重试: knowledge index {path}",
                f"跳过未变更文件: knowledge index {path} --incremental",
            ],
        )

    if as_json:
        _emit_json({"status": "ok", "data": {
            "processed": processed, "skipped": skipped, "failed": failed}})
    else:
        _data_console().print(
            f"[green]✔[/green] 处理 {processed} 个 · 跳过 {skipped} 个 · 失败 {failed} 个"
        )


@app.command()
def search(
    query: str = typer.Argument(..., help="检索查询"),
    top_k: int = typer.Option(5, min=1, max=50, help="返回数量"),
    as_json: bool = typer.Option(False, "--json", help="JSON 输出"),
    plain: bool = typer.Option(False, help="纯文本输出（适合管道）"),
):
    """检索知识片段"""
    from src.vector_store.chroma_client import get_vector_store

    try:
        vs = get_vector_store()
        pairs = vs.similarity_search_with_relevance_scores(query, k=top_k)
    except Exception as e:
        _fail(
            as_json, EXIT_ERROR,
            f"检索失败: {e}",
            "SEARCH_FAILED", "search_failed", recoverable=True,
            suggestions=[
                "检查向量库状态: knowledge doctor",
                "确认已索引数据: knowledge index <path>",
            ],
        )

    results = []
    for doc, score in pairs:
        meta = doc.metadata or {}
        chunk_id = doc.id or meta.get("chunk_id", "")
        section = meta.get("section") or meta.get("heading") or "-"
        results.append({
            "source": meta.get("source", "unknown"),
            "section": section,
            "chunk_id": chunk_id,
            "score": round(float(score), 4),
            "content": doc.page_content[:200],
        })

    if as_json:
        _emit_json({"status": "ok", "data": results})
        return

    if plain:
        for r in results:
            print(f"{r['source']}\t{r['section']}\t{r['chunk_id']}\t{r['score']}\t{r['content']}")
        return

    console = _data_console()
    if not results:
        console.print("[yellow]未找到相关结果[/yellow]")
        return
    table = Table(title=f"检索结果 ({len(results)})", header_style="bold cyan")
    table.add_column("#", justify="right")
    table.add_column("来源", style="bold")
    table.add_column("章节")
    table.add_column("chunk_id")
    table.add_column("分数", justify="right")
    for i, r in enumerate(results, 1):
        table.add_row(str(i), r["source"], r["section"], r["chunk_id"], f"{r['score']:.2f}")
    console.print(table)
    for r in results:
        console.print(f"\n[bold]{r['source']}[/bold] · {r['score']:.2f}")
        console.print(r["content"])


@app.command()
def chat(
    question: str = typer.Argument(..., help="问题"),
    session: str = typer.Option(None, help="恢复会话 ID"),
    as_json: bool = typer.Option(False, "--json", help="JSON 输出"),
):
    """基于知识库回答"""
    from src.api.services.chat import chat_with_rag

    try:
        answer, session_id, elapsed_ms = chat_with_rag(question, session)
    except Exception as e:
        _fail(
            as_json, EXIT_ERROR,
            f"回答失败: {e}",
            "CHAT_FAILED", "chat_failed", recoverable=True,
            suggestions=[
                "检查 DEEPSEEK_API_KEY 配置: knowledge doctor",
                "稍后重试",
            ],
        )

    sources = list(dict.fromkeys(m.strip() for m in _SOURCE_RE.findall(answer)))
    clean = _SOURCE_RE.sub("", answer).strip()

    if as_json:
        _emit_json({"status": "ok", "data": {
            "answer": clean, "sources": sources,
            "session_id": session_id, "elapsed_ms": elapsed_ms,
        }})
        return

    console = _data_console()
    console.print(Panel(Markdown(clean), title="回答", border_style="green"))
    if sources:
        body = "\n".join(f"• {s}" for s in sources)
        console.print(Panel(body, title="引用来源", border_style="blue"))


@app.command()
def status(as_json: bool = typer.Option(False, "--json", help="JSON 输出")):
    """查看系统状态"""
    from config import EMBEDDING_MODEL, LLM_MODEL
    from src.llm import get_llm
    from src.retrieval.retriever import _BM25_PERSIST_PATH
    from src.vector_store.embedding import get_embedding_model
    from src.vector_store.service import VectorStoreService

    embedding = {"name": EMBEDDING_MODEL, "status": "ok"}
    try:
        get_embedding_model()
    except Exception:
        embedding["status"] = "error"

    vector_store = {"chunks": 0, "sources": 0, "status": "error"}
    try:
        stats = VectorStoreService().get_stats()
        vector_store = {"chunks": stats.get("count", 0),
                        "sources": stats.get("source_count", 0),
                        "status": "ok"}
    except Exception:
        pass

    llm = {"name": LLM_MODEL, "status": "ok"}
    try:
        get_llm(temperature=0)
    except Exception:
        llm["status"] = "error"

    bm25 = "ok" if _BM25_PERSIST_PATH.exists() else "missing"
    mcp = "running" if _port_open(8000) else "stopped"

    if as_json:
        _emit_json({"status": "ok", "data": {
            "embedding": embedding,
            "vector_store": vector_store,
            "llm": llm,
            "bm25": bm25,
            "mcp": mcp,
        }})
        return

    console = _data_console()
    table = Table(title="系统状态", header_style="bold cyan")
    table.add_column("组件", style="bold")
    table.add_column("状态")
    table.add_column("详情")
    table.add_row("Embedding", _dot(embedding["status"]), embedding["name"])
    table.add_row("向量库", _dot(vector_store["status"]),
                  f"{vector_store['chunks']} chunks · {vector_store['sources']} 来源")
    table.add_row("LLM", _dot(llm["status"]), llm["name"])
    table.add_row("BM25 索引", "●" if bm25 == "ok" else "○", bm25)
    table.add_row("MCP 服务", "●" if mcp == "running" else "○", mcp)
    console.print(table)


def _dot(status: str) -> str:
    return "● 就绪" if status == "ok" else "○ 错误"


@app.command()
def doctor(
    verbose: bool = typer.Option(False, help="显示修复建议详情"),
    as_json: bool = typer.Option(False, "--json", help="JSON 输出"),
):
    """健康检查"""
    import platform

    from config import DEEPSEEK_API_KEY
    from src.vector_store.embedding import get_embedding_model
    from src.vector_store.service import VectorStoreService

    checks = []

    def add(name, passed, detail="", fix="", critical=False):
        checks.append({"name": name, "passed": passed, "detail": detail,
                       "fix": fix, "critical": critical})

    add("Python", True, detail=platform.python_version())
    add("配置文件 (.env)", Path(".env").exists(),
        fix="创建 .env 文件", critical=True)
    add("DEEPSEEK_API_KEY", bool(DEEPSEEK_API_KEY),
        fix="在 .env 中设置 DEEPSEEK_API_KEY", critical=True)

    missing = []
    for pkg in ["typer", "rich", "click", "fastapi", "uvicorn", "chromadb",
                "sentence_transformers", "jieba", "networkx", "langchain"]:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)
    add("依赖", not missing,
        detail=f"缺失: {', '.join(missing)}" if missing else "完整",
        fix=f"pip install {' '.join(missing)}" if missing else "")

    try:
        get_embedding_model()
        add("Embedding 模型", True)
    except Exception as e:
        add("Embedding 模型", False, detail=str(e), fix="检查 HF_ENDPOINT / 网络")

    try:
        stats = VectorStoreService().get_stats()
        add("向量库", True, detail=f"{stats.get('count', 0)} chunks")
    except Exception as e:
        add("向量库", False, detail=str(e), fix="运行: knowledge index <path>")

    mcp_running = _port_open(8000)
    add("端口 8000", True,
        detail="被占用（服务可能已运行）" if mcp_running else "可用")

    add("MCP 服务", mcp_running,
        detail="运行中" if mcp_running else "未运行",
        fix="运行: knowledge serve")

    if as_json:
        _emit_json({"status": "ok", "data": {
            "checks": checks,
            "passed": sum(1 for c in checks if c["passed"]),
            "total": len(checks),
        }})
    else:
        console = _data_console()
        for c in checks:
            if c["passed"]:
                mark = "[green]✔[/green]"
            else:
                mark = "[red]✖[/red]"
            line = f"{mark} {c['name']}"
            if c["detail"]:
                line += f"  ({c['detail']})"
            console.print(line)
            if not c["passed"] and c["fix"] and (verbose or c["critical"]):
                console.print(f"    [yellow]→ {c['fix']}[/yellow]")

    failed = [c for c in checks if not c["passed"]]
    if failed:
        if any(c["critical"] for c in failed):
            _exit(EXIT_CONFIG)
        _exit(EXIT_ERROR)


@app.command("help")
def help_command(
    ctx: typer.Context,
    topic: str = typer.Argument(None, help="子命令名称"),
):
    """显示命令帮助"""
    import click
    if topic is None:
        typer.echo(ctx.parent.get_help())
        return
    cmd = ctx.parent.command.commands.get(topic)
    if cmd is None:
        _err_console().print(f"[red]未知命令:[/red] {topic}")
        raise typer.Exit(code=2)
    sub_ctx = click.Context(cmd, info_name=topic, parent=ctx.parent)
    typer.echo(cmd.get_help(sub_ctx))


if __name__ == "__main__":
    app()
