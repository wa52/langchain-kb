"""On-demand stdio MCP server for the knowledge base.

opencode spawns this process as a **local** MCP server. It is deliberately
cheap to start: tool registration is instant (so ``tools/list`` answers well
under opencode's 5s timeout) and every heavy resource (embedding model, vector
store, graph, BM25, RAG agent) is initialized lazily in a background warmup
thread, only loaded when a tool that needs it is actually called.

Run:  python -m src.mcp_stdio
"""

import asyncio
import threading

from mcp.server.fastmcp import FastMCP

from src.resources import ResourceManager

mcp = FastMCP("KnowledgeAgent")

_ready = threading.Event()
_start_error: Exception | None = None


def _warmup() -> None:
    """Load every heavy component once, in a daemon thread, before tools call it."""
    global _start_error
    try:
        ResourceManager.get_instance().startup(echo_fn=lambda *a, **k: None)
    except Exception as e:  # pragma: no cover - surfaced by _ensure_ready
        _start_error = e
    finally:
        _ready.set()


def _ensure_ready(timeout: float = 900.0) -> ResourceManager:
    if not _ready.wait(timeout=timeout):
        raise RuntimeError("知识库初始化超时（首次使用需加载模型，请稍后再试）")
    if _start_error is not None:
        raise RuntimeError(f"知识库初始化失败: {_start_error}")
    return ResourceManager.get_instance()


def _task_manager():
    from src.application.indexing import get_task_manager
    return get_task_manager()


# ---------------------------------------------------------------------------
# Read-only tools
# ---------------------------------------------------------------------------


@mcp.tool()
def search_knowledge(query: str, top_k: int = 5) -> dict:
    """在知识库向量库中执行语义搜索，返回相关文档片段（含 source 与 score）。"""
    rm = _ensure_ready()
    from src.application.search import search_documents
    results, elapsed_ms = search_documents(rm, query, top_k)
    return {"results": results, "elapsed_ms": elapsed_ms}


@mcp.tool()
def answer_with_knowledge(query: str, session_id: str | None = None) -> dict:
    """用 RAG Agent 回答问题（检索增强生成），返回答案、来源与会话 id。"""
    _ensure_ready()
    from src.application.chat import chat_with_rag, extract_sources
    answer, sid, elapsed_ms = chat_with_rag(query, session_id)
    return {
        "answer": answer,
        "citations": extract_sources(answer),
        "conversation_id": sid,
        "elapsed_ms": elapsed_ms,
    }


@mcp.tool()
def system_status() -> dict:
    """返回各组件（embedding/LLM/向量库/BM25/图谱/Agent/索引）实时状态与数据规模。"""
    rm = _ensure_ready()
    from src.application.status import get_system_status
    return get_system_status(rm)


@mcp.tool()
def get_index_status(task_id: str) -> dict:
    """查询索引/移除任务状态：pending → running → done / failed。"""
    task = _task_manager().get_task(task_id)
    if task is None:
        raise ValueError(f"任务不存在: {task_id}")
    return {
        "task_id": task["task_id"],
        "status": task["status"],
        "progress": task.get("progress"),
        "result": task.get("result"),
        "error": task.get("error"),
    }


# ---------------------------------------------------------------------------
# Content management tools
# ---------------------------------------------------------------------------


@mcp.tool()
async def start_index_task(path: str, exclude: list[str] | None = None) -> dict:
    """添加文件或目录到知识库（复制到 data/external 并异步索引）。exclude 可跳过相对子路径前缀。"""
    _ensure_ready()
    from src.application.indexing import run_index_task
    mgr = _task_manager()
    if mgr.has_active_task(path):
        raise ValueError(f"已有相同路径的索引任务: {path}")
    task_id = mgr.create_task(path)
    asyncio.create_task(run_index_task(task_id, path, exclude=exclude))
    return {"task_id": task_id, "status": "pending"}


@mcp.tool()
async def upload_documents(name: str, text: str) -> dict:
    """把一段文本作为文件写入 data/external 并异步索引（仅文本文件）。"""
    _ensure_ready()
    from pathlib import Path
    from config import EXTERNAL_DIR
    from src.application.indexing import run_index_task
    base = Path(EXTERNAL_DIR)
    base.mkdir(parents=True, exist_ok=True)
    safe = Path(name or "").name.strip().rstrip(". ")
    if not safe:
        raise ValueError("文件名无效")
    target = base / safe
    counter = 1
    while target.exists():
        target = base / f"{Path(safe).stem}_{counter}{Path(safe).suffix}"
        counter += 1
    target.write_text(text, encoding="utf-8")
    mgr = _task_manager()
    task_id = mgr.create_task(str(target))
    asyncio.create_task(run_index_task(task_id, str(target), in_place=True))
    return {"task_id": task_id, "status": "pending", "saved": target.name}


@mcp.tool()
async def remove_file(name: str, keep_file: bool = False) -> dict:
    """从知识库移除一个文件（删除向量 chunk，可选保留磁盘副本），并重建 BM25。"""
    _ensure_ready()
    from config import EXTERNAL_DIR
    from src.ingestion.pipeline import run_remove
    await asyncio.to_thread(
        run_remove, name, EXTERNAL_DIR, keep_file, (lambda *a, **k: None)
    )
    return {"removed": name, "keep_file": keep_file}


@mcp.tool()
def list_files() -> dict:
    """列出知识库中已跟踪的文件（来源类型 + 相对路径 + 指纹）。"""
    from src.application.files import list_files_view
    return list_files_view()


# ---------------------------------------------------------------------------
# Session management
# ---------------------------------------------------------------------------


@mcp.tool()
def list_sessions() -> dict:
    """列出历史会话（标题、创建时间、轮数），按时间倒序。"""
    from src.application.sessions import list_sessions
    return {"sessions": list_sessions()}


@mcp.tool()
def delete_session(session_id: str) -> dict:
    """删除一个历史会话。"""
    from src.application.sessions import delete_history
    if not delete_history(session_id):
        raise ValueError(f"会话不存在: {session_id}")
    return {"deleted": session_id}


# ---------------------------------------------------------------------------
# Settings & scheduled sync
# ---------------------------------------------------------------------------


@mcp.tool()
def set_graph_extraction_mode(enabled: bool) -> dict:
    """切换知识图谱抽取模式：True=LLM（DeepSeek，慢但质量高），False=jieba（本地快）。"""
    from src.application.settings import set_graph_extraction_mode as _svc
    return _svc(enabled)


@mcp.tool()
def get_sync_status() -> dict:
    """查询经验库定时同步的配置与最近一次运行结果。"""
    from src.application import sync
    return sync.get_sync_view()


@mcp.tool()
def add_sync_dir(path: str) -> dict:
    """把一个服务器本机目录加入定时同步列表。"""
    from src.application import sync
    return sync.add_sync_dir(path)


@mcp.tool()
def remove_sync_dir(path: str) -> dict:
    """从定时同步列表移除一个目录。"""
    from src.application import sync
    return sync.remove_sync_dir(path)


@mcp.tool()
async def run_sync() -> dict:
    """立即后台执行一次经验库增量同步。"""
    _ensure_ready()
    from src.application import sync
    started = await sync.run_sync_now()
    return {"running": True, "started": started}


def main() -> None:
    threading.Thread(target=_warmup, daemon=True).start()
    mcp.run()


if __name__ == "__main__":
    main()
