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
        "  knowledge web\n"
        "  knowledge cli\n"
        '  knowledge search "什么是RAG?"\n'
        "  knowledge index ./docs\n"
        "\n聊天、检索建议优先使用 Web 客户端: knowledge web"
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
    ("web", "启动 Web 服务（首页 + API + MCP）"),
    ("cli", "进入交互式问答控制台（建议优先使用 Web）"),
    ("search", "检索知识片段（建议优先使用 Web 检索）"),
    ("chat", "基于知识库回答（建议优先使用 Web 聊天）"),
    ("index", "索引文件或目录到向量库"),
    ("map", "查看能力模型与知识覆盖"),
    ("project", "按能力阶段引导工业视觉项目"),
    ("design", "根据需求生成初版工业视觉方案"),
    ("status", "查看系统状态"),
    ("doctor", "健康检查"),
    ("sync-experience", "增量同步经验库目录（EXPERIENCE_DIRS）"),
    ("serve", "启动 API + MCP 服务"),
]


def _print_concise_help():
    typer.echo(f"{PRODUCT_NAME}命令行工具")
    typer.echo()
    typer.echo("用法: knowledge [命令] [选项]")
    typer.echo()
    typer.echo("示例:")
    typer.echo("  knowledge web")
    typer.echo("  knowledge cli")
    typer.echo('  knowledge search "什么是RAG?"')
    typer.echo("  knowledge index ./docs")
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
    from config import ensure_data_dirs
    ensure_data_dirs()
    _ensure_llm_api_key_if_needed(ctx.invoked_subcommand)
    if ctx.invoked_subcommand is None:
        _print_concise_help()


_LLM_COMMANDS = frozenset({"web", "cli", "serve", "chat"})


def _ensure_llm_api_key_if_needed(subcommand: str | None):
    """On first run, prompt for a DeepSeek API key when an LLM-backed command
    is invoked and no key is configured. Non-interactive environments skip."""
    if subcommand not in _LLM_COMMANDS:
        return
    from config import DEEPSEEK_API_KEY
    if DEEPSEEK_API_KEY:
        return
    from src.cli.api_key import ensure_api_key
    ensure_api_key()


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
def web(
    host: str = typer.Option("127.0.0.1", help="监听地址"),
    port: int = typer.Option(8000, help="监听端口"),
    reload: bool = typer.Option(False, help="开发模式自动重载"),
    open_browser: bool = typer.Option(False, "--open", help="启动后打开浏览器"),
    as_json: bool = typer.Option(False, "--json", help="JSON 输出"),
):
    """启动 Web 服务（Web 首页 + API 文档 + MCP）"""
    _serve(host, port, reload, as_json, open_browser=open_browser)


@app.command()
def cli():
    """进入交互式问答控制台（建议优先使用 Web 聊天）"""
    from src.cli.console import run_console
    run_console()


def _serve(host, port, reload, as_json, open_browser=False):
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
        if open_browser and not as_json:
            import webbrowser
            webbrowser.open(f"{url}/")
        uvicorn.run(app_obj, host=host, port=port, reload=reload, log_level="info")
    except OSError as e:
        _fail(
            as_json, EXIT_TRANSIENT,
            f"端口 {port} 被占用: {e}",
            "PORT_BUSY", "port_busy", recoverable=True,
            suggestions=[
                f"换一个端口: knowledge web --port {port + 1}",
                f"检查占用进程: netstat -ano | findstr :{port}",
            ],
        )


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", help="监听地址"),
    port: int = typer.Option(8000, help="监听端口"),
    reload: bool = typer.Option(False, help="开发模式自动重载"),
    as_json: bool = typer.Option(False, "--json", help="JSON 输出"),
):
    """启动 API + MCP 服务"""
    _serve(host, port, reload, as_json)


@app.command("sync-experience")
def sync_experience_command(
    as_json: bool = typer.Option(False, "--json", help="JSON 输出"),
):
    """增量同步经验库目录（EXPERIENCE_DIRS，分号分隔的绝对路径）"""
    from src.ingestion.pipeline import sync_experience

    echo = _PipelineEcho(_err_console(), enabled=not as_json)
    result = sync_experience(echo_fn=echo)
    echo.finish()
    if as_json:
        _emit_json({"status": "ok", "data": result})
    else:
        _data_console().print(
            f"[green]✔[/green] 经验同步完成: "
            f"{result['dirs']} 目录 · 变更 {result['changed']} · "
            f"新增 {result['chunks']} 片段"
        )


@app.command()
def lark(as_json: bool = typer.Option(False, "--json", help="JSON 输出")):
    """启动飞书机器人（长连接模式，无需公网 URL）"""
    import os as _os

    from src.feishu.bot import get_feishu_credentials, run_feishu_bot

    app_id, _secret = get_feishu_credentials()
    if not app_id or not _secret:
        _fail(
            as_json, EXIT_CONFIG,
            "FEISHU_APP_ID / FEISHU_APP_SECRET 未配置",
            "FEISHU_NOT_CONFIGURED", "feishu_not_configured", recoverable=True,
            suggestions=[
                "在 .env 中配置飞书应用凭证（.env.example 有模板）",
                "运行 knowledge doctor 检查环境",
            ],
        )
        return
    if as_json:
        _emit_json({"status": "ok", "data": {"app_id": app_id}})
    else:
        _data_console().print(Panel(
            f"[bold]飞书机器人:[/bold] {app_id}\n"
            "[bold]连接方式:[/bold] 长连接（WebSocket）\n"
            "[bold]知识库 API:[/bold] " + _os.getenv("KB_API_BASE", "http://127.0.0.1:8000"),
            title="飞书机器人",
            border_style="cyan",
        ))
    run_feishu_bot()


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
    capability: str = typer.Option(None, "--capability", help="按能力域过滤（1-7）"),
    as_json: bool = typer.Option(False, "--json", help="JSON 输出"),
    plain: bool = typer.Option(False, help="纯文本输出（适合管道）"),
):
    """检索知识片段（可用 --capability 按能力域过滤；建议优先使用 Web 检索）"""
    try:
        if capability:
            from src.vector_store.service import VectorStoreService
            retriever = VectorStoreService().get_retriever(k=top_k, capability=capability)
            docs = retriever.invoke(query)
            results = []
            for doc in docs:
                meta = doc.metadata or {}
                chunk_id = doc.id or meta.get("chunk_id", "")
                section = meta.get("section") or meta.get("heading") or "-"
                results.append({
                    "source": meta.get("source", "unknown"),
                    "section": section,
                    "chunk_id": chunk_id,
                    "score": None,
                    "content": doc.page_content[:200],
                })
        else:
            from src.vector_store.chroma_client import get_vector_store
            vs = get_vector_store()
            pairs = vs.similarity_search_with_relevance_scores(query, k=top_k)
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
    question: str = typer.Argument(None, help="问题（不带则进入交互式对话）"),
    session: str = typer.Option(None, help="恢复会话 ID"),
    as_json: bool = typer.Option(False, "--json", help="JSON 输出"),
):
    """基于知识库回答（不带问题参数时进入交互式对话；建议优先使用 Web 聊天）"""
    if question is None:
        from src.cli.console import run_console
        run_console()
        return

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
    """查看系统状态（与 Web 状态页同一组件模型）"""
    from config import DATA_DIR, EMBEDDING_MODEL, GRAPH_PERSIST_DIR, KNOWLEDGE_HOME, LLM_MODEL
    from src.llm import get_llm
    from src.retrieval.retriever import _BM25_PERSIST_PATH
    from src.status import overall_state
    from src.vector_store.embedding import get_embedding_model
    from src.vector_store.service import VectorStoreService

    embedding = {"name": EMBEDDING_MODEL, "status": "ready"}
    try:
        get_embedding_model()
    except Exception:
        embedding["status"] = "error"

    vector_store = {"chunks": 0, "sources": 0, "status": "error"}
    try:
        stats = VectorStoreService().get_stats()
        vector_store = {"chunks": stats.get("count", 0),
                        "sources": stats.get("source_count", 0),
                        "status": "ready"}
    except Exception:
        pass

    llm = {"name": LLM_MODEL, "status": "ready"}
    try:
        get_llm(temperature=0)
    except Exception:
        llm["status"] = "error"

    bm25_state = "ready" if _BM25_PERSIST_PATH.exists() else "pending"
    graph_state, graph_nodes, graph_detail = _graph_status(GRAPH_PERSIST_DIR)

    # 与 Web 状态页（System Rail / /api/v1/status）一致的组件模型
    components = {
        "embedding": {"state": embedding["status"], "detail": EMBEDDING_MODEL},
        "llm": {"state": llm["status"], "detail": LLM_MODEL},
        "vector_store": {
            "state": vector_store["status"],
            "detail": f"{vector_store['chunks']} chunks · {vector_store['sources']} 来源",
        },
        "bm25": {"state": bm25_state, "detail": "磁盘缓存就绪" if bm25_state == "ready" else "未构建"},
        "graph": {"state": graph_state, "detail": graph_detail},
        "agent": {"state": "pending", "detail": "会话时按需加载"},
        "index": {"state": "pending", "detail": "无活动任务"},
    }
    overall = overall_state(components)

    mcp = "running" if _port_open(8000) else "stopped"
    home_status = "ok" if Path(KNOWLEDGE_HOME).exists() else "error"
    docs_status = "ok" if Path(DATA_DIR).exists() else "error"

    if as_json:
        _emit_json({"status": "ok", "data": {
            "knowledge_home": str(KNOWLEDGE_HOME),
            "data_dir": str(DATA_DIR),
            "embedding": {"name": EMBEDDING_MODEL, "status": embedding["status"]},
            "vector_store": vector_store,
            "llm": {"name": LLM_MODEL, "status": llm["status"]},
            "bm25": bm25_state,
            "mcp": mcp,
            "overall": overall,
            "graph_nodes": graph_nodes,
            "components": {name: {"state": c["state"], "detail": c["detail"]}
                           for name, c in components.items()},
        }})
        return

    console = _data_console()
    table = Table(title="系统状态", header_style="bold cyan")
    table.add_column("组件", style="bold")
    table.add_column("状态")
    table.add_column("详情")
    table.add_row("数据目录", _dot(home_status), str(KNOWLEDGE_HOME))
    table.add_row("源文档目录", _dot(docs_status), str(DATA_DIR))
    table.add_row("整体状态", _state_mark(overall), "core: embedding/llm/vector_store")
    table.add_row("Embedding", _state_mark(embedding["status"]), embedding["name"])
    table.add_row("向量库", _state_mark(vector_store["status"]),
                  f"{vector_store['chunks']} chunks · {vector_store['sources']} 来源")
    table.add_row("LLM", _state_mark(llm["status"]), llm["name"])
    table.add_row("BM25 索引", _state_mark(bm25_state),
                  "磁盘缓存就绪" if bm25_state == "ready" else "未构建")
    table.add_row("知识图谱", _state_mark(graph_state), graph_detail)
    table.add_row("组件链路",
                  " | ".join(f"{name} {_state_mark(c['state'])[0]}"
                             for name, c in components.items()),
                  "与 Web 状态页一致")
    table.add_row("MCP 服务", "●" if mcp == "running" else "○", mcp)
    console.print(table)


def _state_mark(state: str) -> str:
    if state == "ready" or state == "ok":
        return "● 就绪"
    if state == "error":
        return "✖ 错误"
    return "○ 等待"


def _graph_status(graph_persist_dir) -> tuple[str, int, str]:
    """确定性图谱探针：文件缺失→pending，损坏→error，实体为空→pending。"""
    path = Path(graph_persist_dir) / "knowledge_graph.json"
    if not path.exists():
        return "pending", 0, "未构建"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        nodes = data.get("nodes") or []
        n = len(nodes) if isinstance(nodes, list) else 0
    except Exception:
        return "error", 0, "文件损坏"
    if n == 0:
        return "pending", 0, "实体为空"
    return "ready", n, f"{n} 个实体"


def _dot(status: str) -> str:
    return "● 就绪" if status == "ok" else "○ 错误"


@app.command()
def doctor(
    verbose: bool = typer.Option(False, help="显示修复建议详情"),
    as_json: bool = typer.Option(False, "--json", help="JSON 输出"),
):
    """健康检查"""
    import platform

    from config import DATA_DIR, DEEPSEEK_API_KEY, KNOWLEDGE_HOME
    from src.vector_store.embedding import get_embedding_model
    from src.vector_store.service import VectorStoreService

    checks = []

    def add(name, passed, detail="", fix="", critical=False):
        checks.append({"name": name, "passed": passed, "detail": detail,
                       "fix": fix, "critical": critical})

    add("Python", True, detail=platform.python_version())
    add("数据目录", Path(KNOWLEDGE_HOME).exists(),
        detail=str(KNOWLEDGE_HOME),
        fix="设置 KNOWLEDGE_HOME 指向已存在的目录")
    add("源文档目录", Path(DATA_DIR).exists(),
        detail=str(DATA_DIR),
        fix="把文档放入该目录或运行: knowledge index <path>")
    add("配置文件 (.env)", (Path(KNOWLEDGE_HOME) / ".env").exists(),
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


@app.command("project")
def project_command(
    project_desc: str = typer.Argument(..., help="项目描述，如 'PCB 表面缺陷检测'"),
    stage: str = typer.Option("需求分析", "--stage", help="项目阶段（需求分析/知识研究/方案设计/算法实现/工程开发/项目验证，或 1-6）"),
    as_json: bool = typer.Option(False, "--json", help="JSON 输出"),
):
    """按工业视觉项目阶段引导项目推进"""
    from src.agent.project_workflow import project_workflow, PROJECT_STAGES

    try:
        text = project_workflow.func(project_desc=project_desc, stage=stage)
    except Exception as e:
        _fail(as_json, EXIT_ERROR, f"引导失败: {e}",
              "PROJECT_FAILED", "project_failed", recoverable=True,
              suggestions=["检查向量库状态: knowledge doctor"])

    if as_json:
        stage_info = None
        for s in PROJECT_STAGES:
            if stage in (s["name"], str(s["id"])) or stage in s["name"]:
                stage_info = s
                break
        _emit_json({
            "status": "ok",
            "data": {
                "project": project_desc,
                "stage": stage_info["name"] if stage_info else stage,
                "guidance": text,
            },
        })
        return

    console = _data_console()
    console.print(Markdown(text))


@app.command("design")
def design_command(
    project_desc: str = typer.Argument(..., help="项目描述，如 'PCB 表面缺陷检测'"),
    llm_check: bool = typer.Option(False, "--llm-check", help="生成后执行方案质量/风险/完整性检查"),
    as_json: bool = typer.Option(False, "--json", help="JSON 输出"),
):
    """根据项目需求生成初版工业视觉方案（输出到 data/projects/）"""
    import time as _t
    from config import KNOWLEDGE_HOME, LLM_MODEL
    from src.llm import get_llm
    from src.agent.requirement_analyzer import analyze_requirement
    from src.agent.algorithm_selector import select_algorithm_llm
    from src.agent.solution_generator import generate_solution
    from src.agent.project_report import write_report, log_llm_call, write_check_report

    llm = get_llm(temperature=0)
    project_dir = Path(KNOWLEDGE_HOME) / "data" / "projects" / _safe_name(project_desc)
    logs = []

    def _log(stage, prompt, response, seconds, success=True, error=""):
        logs.append({
            "project_name": _safe_name(project_desc),
            "stage": stage,
            "prompt_summary": prompt,
            "model": LLM_MODEL,
            "response_summary": response,
            "execution_time_s": seconds,
            "success": success,
            "error": error,
        })

    try:
        # 1) 需求解析（1 次 LLM）
        t0 = _t.time()
        requirement = analyze_requirement(project_desc, llm)
        _log("requirement_analyze", f"解析需求: {project_desc[:50]}",
             f"product={requirement['product']}, task={requirement['task']}",
             _t.time() - t0)

        # 2) 算法推荐（规则表 + cap4 检索 + LLM 算子细化）
        t0 = _t.time()
        algorithm = select_algorithm_llm(requirement["task"], requirement.get("scene", ""), llm=llm)
        _log("algorithm_select", f"任务: {requirement['task']}",
             f"算法: {','.join(algorithm['algorithms'])}; 算子: {','.join(algorithm.get('operators', []))}",
             _t.time() - t0)

        # 3) 方案生成（1 次 LLM）
        t0 = _t.time()
        solution = generate_solution(requirement, algorithm, llm)
        _log("solution_generate", f"生成方案: {project_desc[:50]}",
             "10 节方案", _t.time() - t0)

        # 4) 组装各文档
        sections = _assemble_sections(requirement, algorithm, solution)
        written = write_report(project_dir, sections)

        # 5) 可选 LLM 检查
        check_text = ""
        if llm_check:
            t0 = _t.time()
            check_text = _run_llm_check(project_desc, sections, llm)
            write_check_report(project_dir, check_text)
            _log("llm_check", f"方案检查: {project_desc[:50]}", "check_report", _t.time() - t0)

        for rec in logs:
            log_llm_call(project_dir, rec)

    except Exception as e:
        if as_json:
            _fail(as_json, EXIT_ERROR, f"方案生成失败: {e}",
                  "DESIGN_FAILED", "design_failed", recoverable=True,
                  suggestions=["检查 DEEPSEEK_API_KEY: knowledge doctor"])
        raise

    if as_json:
        _emit_json({"status": "ok", "data": {
            "project": project_desc,
            "output_dir": str(project_dir),
            "files": written,
            "requirement": requirement,
            "algorithm": algorithm,
            "llm_checks": bool(check_text),
            "llm_calls": len(logs),
        }})
        return

    console = _data_console()
    console.print(f"[bold green]方案已生成: {project_dir}[/bold green]")
    for f in written:
        console.print(f"  {f}")
    if check_text:
        console.print("  含 check_report.md")
    console.print(f"\nLLM 调用次数: {len(logs)}")


def _safe_name(name: str) -> str:
    import re as _re
    return _re.sub(r'[\\/:*?"<>|]', "_", name).strip() or "project"


def _assemble_sections(requirement: dict, algorithm: dict, solution: dict) -> dict:
    """Assemble the 5 output markdown documents from the generated solution."""
    req_lines = [
        "# 需求分析",
        "",
        f"**产品**: {requirement.get('product', '')}",
        f"**检测任务**: {requirement.get('task', '')}",
        f"**检测目标**: {requirement.get('target', '')}",
        f"**精度要求**: {requirement.get('precision', '')}",
        f"**速度要求**: {requirement.get('speed', '')}",
        f"**环境约束**: {requirement.get('environment', '')}",
    ]
    if requirement.get("unknown"):
        req_lines += ["", "**未明确项**:"] + [f"- {u}" for u in requirement["unknown"]]

    sol_body = "\n\n".join(
        f"## {s['title']}\n\n{s['content']}" for s in solution["sections"]
    )

    alg_lines = [
        "# 算法方案",
        "",
        f"**任务**: {algorithm.get('task', '')}",
        f"**推荐算法**: {', '.join(algorithm.get('algorithms', []))}",
        f"**选择理由**: {algorithm.get('reason', '')}",
    ]
    if algorithm.get("operators"):
        alg_lines += ["", "**具体算子/API**:"] + [
            f"- {op}" for op in algorithm["operators"]
        ]
    if algorithm.get("llm_refinements"):
        alg_lines += ["", "**LLM 细化建议**:", "", algorithm["llm_refinements"]]
    if algorithm.get("knowledge_refs"):
        alg_lines += ["", "**知识参考**:"] + [
            f"- [{r['source']}] {r['content'][:150]}" for r in algorithm["knowledge_refs"]
        ]

    risk_lines = [
        "# 风险分析",
        "",
        "（由方案生成结果中的'风险分析'章节提炼）",
        "",
        _section_content(solution, "risk"),
    ]

    q_lines = [
        "# 待确认问题",
        "",
        "以下问题需与客户/现场确认后才能细化方案：",
        "",
    ]
    if requirement.get("unknown"):
        q_lines += [f"- [ ] {u}" for u in requirement["unknown"]]
    q_lines += ["", "（来自方案'待确认问题'章节）", "", _section_content(solution, "questions")]

    return {
        "requirement": "\n".join(req_lines),
        "solution": f"# 项目方案: {requirement.get('product', '')}\n\n{sol_body}",
        "algorithm": "\n".join(alg_lines),
        "risk": "\n".join(risk_lines),
        "questions": "\n".join(q_lines),
    }


def _section_content(solution: dict, key: str) -> str:
    for s in solution.get("sections", []):
        if s.get("key") == key:
            return s.get("content", "")
    return ""


def _run_llm_check(project_desc: str, sections: dict, llm) -> str:
    """Optional quality/risk/completeness check (1 LLM call)."""
    body = sections.get("solution", "")[:3000]
    prompt = (
        "你是一名工业视觉方案评审专家。请对以下项目方案进行三方面检查，输出中文报告：\n"
        "1. 方案质量（成像/算法是否合理、有无明显错误）\n"
        "2. 风险遗漏（是否有未考虑的风险）\n"
        "3. 完整性（是否缺少关键环节）\n\n"
        f"项目: {project_desc}\n\n方案摘要:\n{body}"
    )
    try:
        return llm.invoke(prompt).content.strip()
    except Exception as e:
        return f"检查失败: {e}"


@app.command("map")
def map_command(
    capability: str = typer.Option(None, help="查看指定能力域（如 4 算法实现）下的知识"),
    rebuild: bool = typer.Option(False, "--rebuild", help="对向量库中缺少能力标签的 chunks 补打标签"),
    as_json: bool = typer.Option(False, "--json", help="JSON 输出"),
):
    """查看工业视觉 AI 能力模型与知识覆盖"""
    from collections import Counter
    from src.capability.model import CAPABILITY_DOMAINS, DOMAIN_BY_ID
    from src.vector_store.chroma_client import get_vector_store

    vs = get_vector_store()

    if rebuild:
        _map_rebuild(vs, echo_fn=lambda m: _err_console().print(m))

    # 统计每个能力域覆盖的 chunks
    counts = Counter()
    scene_counts = Counter()
    tech_counts = Counter()
    source_by_domain: dict[int, set] = {d["id"]: set() for d in CAPABILITY_DOMAINS}
    offset = 0
    while True:
        batch = vs._collection.get(include=["metadatas"], limit=500, offset=offset)
        metas = batch.get("metadatas") or []
        if not metas:
            break
        for m in metas:
            m = m or {}
            doms = (m.get("capability_domain") or "").split(",")
            for d in doms:
                if d.isdigit():
                    counts[int(d)] += 1
                    source_by_domain.setdefault(int(d), set()).add(m.get("source", ""))
            sc = m.get("scene")
            if sc:
                scene_counts[sc] += 1
            tech = m.get("technology")
            if tech:
                tech_counts[tech] += 1
        offset += 500

    if capability:
        _map_show_domain(int(capability), counts, source_by_domain, as_json)
        return

    if as_json:
        _emit_json({
            "status": "ok",
            "data": {
                "domains": [
                    {"id": d["id"], "name": d["name"], "chunks": counts.get(d["id"], 0),
                     "sources": len(source_by_domain.get(d["id"], set()))}
                    for d in CAPABILITY_DOMAINS
                ],
                "scenes": dict(scene_counts),
                "technologies": dict(tech_counts),
                "total_chunks": sum(counts.values()),
            },
        })
        return

    console = _data_console()
    console.print("[bold]工业视觉 AI 工程师能力模型[/bold]")
    console.print("（知识按 AI 能力组织，来源仅为辅助维度）\n")
    table = Table(title="能力域知识覆盖", header_style="bold cyan")
    table.add_column("ID", justify="right")
    table.add_column("能力域")
    table.add_column("chunks", justify="right")
    table.add_column("来源数", justify="right")
    for d in CAPABILITY_DOMAINS:
        table.add_row(
            str(d["id"]), d["name"],
            str(counts.get(d["id"], 0)),
            str(len(source_by_domain.get(d["id"], set()))),
        )
    console.print(table)

    if scene_counts:
        console.print("\n[bold]场景分布[/bold]")
        for sc, n in scene_counts.most_common(12):
            console.print(f"  {sc}: {n}")
    if tech_counts:
        console.print("\n[bold]技术分布[/bold]")
        for t, n in tech_counts.most_common(10):
            console.print(f"  {t}: {n}")


def _map_show_domain(dom_id: int, counts, source_by_domain, as_json: bool):
    from src.capability.model import DOMAIN_BY_ID
    domain = DOMAIN_BY_ID.get(dom_id)
    if domain is None:
        _fail(as_json, EXIT_ERROR, f"未知能力域: {dom_id}（有效 1-7）",
              "MAP_BAD_DOMAIN", "bad_domain", recoverable=False)
    sources = sorted(source_by_domain.get(dom_id, set()))
    if as_json:
        _emit_json({"status": "ok", "data": {
            "id": dom_id, "name": domain["name"],
            "items": domain["items"], "chunks": counts.get(dom_id, 0),
            "sources": sources,
        }})
        return
    console = _data_console()
    console.print(f"[bold]能力域 {dom_id}: {domain['name']}[/bold]")
    for it in domain["items"]:
        console.print(f"  {it}")
    console.print(f"\n覆盖 chunks: [bold]{counts.get(dom_id, 0)}[/bold] · 来源: {len(sources)}")
    if sources:
        console.print("\n[bold]相关来源:[/bold]")
        for s in sources[:30]:
            console.print(f"  {s}")
        if len(sources) > 30:
            console.print(f"  ... 共 {len(sources)} 个来源")


def _map_rebuild(vs, echo_fn=print):
    """Backfill capability metadata on chunks that lack it (rule-based, no LLM)."""
    from src.capability.mapper import classify_chunk

    missing_ids = []
    missing_sources = []
    missing_texts = []
    offset = 0
    while True:
        batch = vs._collection.get(
            include=["metadatas", "documents"], limit=500, offset=offset)
        metas = batch.get("metadatas") or []
        docs = batch.get("documents") or []
        ids = batch.get("ids") or []
        if not ids:
            break
        for cid, m, d in zip(ids, metas, docs):
            m = m or {}
            if "capability_domain" not in m or "capability_domain_primary" not in m:
                missing_ids.append(cid)
                missing_sources.append(m.get("source", ""))
                missing_texts.append(d or "")
        offset += 500

    echo_fn(f"  -> 缺少能力标签的 chunks: {len(missing_ids)}")
    if not missing_ids:
        return

    batch = 500
    for i in range(0, len(missing_ids), batch):
        id_slice = missing_ids[i:i + batch]
        meta_slice = []
        for src, txt in zip(missing_sources[i:i + batch], missing_texts[i:i + batch]):
            tags = classify_chunk(src, txt)
            tags.pop("source", None)
            meta_slice.append(tags)
        vs._collection.update(ids=id_slice, metadatas=meta_slice)
    echo_fn(f"  -> 已为 {len(missing_ids)} 个 chunks 补打能力标签")


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
