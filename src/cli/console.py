import os

from config import (
    DATA_DIR, EXTERNAL_DIR,
    ENABLE_GRADING, ENABLE_REWRITE, ENABLE_HYBRID_SEARCH,
    ENABLE_CONTEXT_COMPRESSION, ENABLE_GRAPH, ENABLE_GRAPH_LLM_EXTRACTION,
)
from src.agent.chat_history import save_history, load_history, list_sessions, compress_history
from langchain_openai import ChatOpenAI
from config import LLM_MODEL, DEEPSEEK_API_KEY, DEEPSEEK_API_BASE
from src.agent.rag_agent import create_rag_agent, stream_rag_response
from src.ingestion.pipeline import run_ingestion, run_incremental_update, run_add_path, run_remove
from src.vector_store.chroma_client import get_vector_store, reset_vector_store
from src.vector_store.embedding import get_embedding_model
from src.cli.commands import echo

try:
    from prompt_toolkit import prompt as pt_prompt
    from prompt_toolkit.completion import Completer, Completion
    _HAS_PROMPT_TOOLKIT = True
except ImportError:
    _HAS_PROMPT_TOOLKIT = False


SLASH_COMMANDS = [
    "/help", "/new", "/sessions", "/resume", "/add", "/files",
    "/remove", "/mode", "/ingest", "/rebuild", "/stats", "/config",
    "/clear", "/exit",
]


if _HAS_PROMPT_TOOLKIT:
    class SlashCompleter(Completer):
        def get_completions(self, document, complete_event):
            text = document.text_before_cursor
            if not text.startswith("/"):
                return
            for cmd in SLASH_COMMANDS:
                if cmd.startswith(text):
                    yield Completion(cmd, start_position=-len(text))
else:
    class SlashCompleter:
        pass


def _get_user_input(prompt_text: str) -> str:
    if _HAS_PROMPT_TOOLKIT:
        return pt_prompt(prompt_text, completer=SlashCompleter())
    return input(prompt_text)


def get_status_bar(state: dict) -> str:
    mode = "LLM" if ENABLE_GRAPH_LLM_EXTRACTION else "jieba"
    session_id = state.get("session_id")
    msgs = state.get("messages", [])
    turns = len([m for m in msgs if m["role"] == "user"])
    session_label = f"会话_{session_id[:12]}" if session_id else "新对话"
    session_info = f"{session_label} ({turns}轮)" if turns else session_label
    try:
        from src.ingestion.tracker import list_all_files
        all_files = list_all_files()
        file_count = len(all_files)
    except Exception:
        file_count = "?"
    try:
        from src.vector_store.chroma_client import get_collection_stats
        stats = get_collection_stats()
        chunk_count = stats.get("count", "?")
    except Exception:
        chunk_count = "?"
    try:
        from src.graph_store.retriever import get_graph
        g = get_graph()
        entity_count = g.graph.number_of_nodes()
    except Exception:
        entity_count = "?"
    bar = (
        "╔══════════════════════════════════════════════════════════╗\n"
        f"║  LangChain RAG 知识库    {file_count} 文件 · {chunk_count} 块 · {entity_count} 实体 · {mode} 模式  ║\n"
        f"║  {session_info:<53}║\n"
        "╚══════════════════════════════════════════════════════════╝"
    )
    return bar


def handle_command(line: str, state: dict) -> str | None:
    line = line.strip()
    if not line:
        return ""
    if not line.startswith("/"):
        return None
    parts = line.split(maxsplit=1)
    cmd = parts[0].lower()
    arg = parts[1] if len(parts) > 1 else ""

    if cmd == "/exit":
        return None
    if cmd == "/clear":
        os.system("cls" if os.name == "nt" else "clear")
        return "\n" + get_status_bar(state)

    if cmd == "/help":
        lines = [
            "可用命令:",
            "  /help               显示帮助",
            "  /new                新对话",
            "  /sessions           历史会话列表",
            "  /resume <id>        恢复历史会话",
            "  /add <path>         添加资料",
            "  /files              资料列表",
            "  /remove <name>      删除资料",
            "  /mode [llm|jieba]   切换图谱抽取模式",
            "  /ingest             全量导入",
            "  /rebuild            重建索引",
            "  /stats              知识库统计",
            "  /config             当前配置",
            "  /clear              清屏",
            "  /exit               退出",
            "直接输入问题开始对话。",
        ]
        return "\n".join(lines)

    if cmd == "/new":
        state["messages"] = []
        state["session_id"] = None
        return "\n" + get_status_bar(state)

    if cmd == "/sessions":
        sessions = list_sessions()
        if not sessions:
            return "暂无历史会话"
        lines = [f"{'会话ID':<25} {'时间':<20} {'消息数':<8}"]
        lines.append("-" * 55)
        for s in sessions:
            try:
                msgs = load_history(s["id"])
                n = len([m for m in msgs if m["role"] == "user"]) if msgs else 0
            except Exception:
                n = "?"
            lines.append(f"{s['id']:<25} {s['created']:<20} {str(n):<8}")
        return "\n".join(lines)

    if cmd == "/resume":
        if not arg:
            return "用法: /resume <会话ID>"
        msgs = load_history(arg)
        if msgs is None:
            return f"未找到会话: {arg}"
        state["messages"] = msgs
        state["session_id"] = arg
        turns = len([m for m in msgs if m["role"] == "user"])
        return f"已恢复会话 {arg} ({turns}轮)" + "\n" + get_status_bar(state)

    if cmd == "/add":
        if not arg:
            return "用法: /add <文件路径>"
        count = run_add_path(arg, EXTERNAL_DIR)
        return f"成功添加 {count} 个文档片段"

    if cmd == "/files":
        from src.ingestion.tracker import list_all_files
        files = list_all_files()
        if not files:
            return "暂无文件记录"
        lines = [f"{'来源':<8} {'文件':<30}", f"{'----':<8} {'----':<30}"]
        for f in sorted(files, key=lambda x: (x["source_type"], x["file_key"])):
            label = "内部" if f["source_type"] == "internal" else "外部"
            lines.append(f"{label:<8} {f['file_key']:<30}")
        return "\n".join(lines)

    if cmd == "/remove":
        if not arg:
            return "用法: /remove <文件名>"
        run_remove(arg, EXTERNAL_DIR)
        return f"已处理: {arg}"

    if cmd == "/mode":
        import config as cfg
        from dotenv import find_dotenv, set_key
        if not arg:
            current = "LLM" if cfg.ENABLE_GRAPH_LLM_EXTRACTION else "jieba"
            return f"当前抽取模式: {current}"
        if arg not in ("llm", "jieba"):
            return "用法: /mode [llm|jieba]"
        dotenv_path = find_dotenv()
        if not dotenv_path:
            return "错误: 未找到 .env 文件"
        is_llm = arg == "llm"
        set_key(dotenv_path, "ENABLE_GRAPH_LLM_EXTRACTION", "true" if is_llm else "false")
        os.environ["ENABLE_GRAPH_LLM_EXTRACTION"] = "true" if is_llm else "false"
        cfg.ENABLE_GRAPH_LLM_EXTRACTION = is_llm
        return f"切换到 {arg.upper()} 抽取模式（立即生效）"

    if cmd == "/ingest":
        echo("全量导入中...")
        count = run_ingestion(DATA_DIR)
        return f"成功导入 {count} 个文档片段"

    if cmd == "/rebuild":
        confirm = input("这将清空现有数据库，确定继续？(y/n) ")
        if confirm.lower() != "y":
            return "已取消"
        reset_vector_store()
        embeddings = get_embedding_model()
        vs = get_vector_store(embeddings)
        vs.delete_collection()
        reset_vector_store()
        count = run_ingestion(DATA_DIR)
        return f"重建完成，导入 {count} 个片段"

    if cmd == "/stats":
        from src.vector_store.chroma_client import get_collection_stats
        from src.ingestion.tracker import list_all_files
        stats = get_collection_stats()
        lines = ["=" * 40, "知识库统计", "=" * 40]
        lines.append(f"  向量总数:        {stats['count']}")
        lines.append(f"  来源文件数:      {stats['source_count']}")
        files = list_all_files()
        int_cnt = len([f for f in files if f["source_type"] == "internal"])
        ext_cnt = len([f for f in files if f["source_type"] == "external"])
        lines.append(f"  内部文件:        {int_cnt}")
        lines.append(f"  外部文件:        {ext_cnt}")
        if stats["sources"]:
            lines.append(f"  ── 来源文件列表 ──")
            for s in stats["sources"][:30]:
                lines.append(f"    {s}")
            if len(stats["sources"]) > 30:
                lines.append(f"    ... 还有 {len(stats['sources']) - 30} 个文件")
        return "\n".join(lines)

    if cmd == "/config":
        lines = [
            "=" * 40,
            "当前配置",
            "=" * 40,
            f"  数据目录:          {DATA_DIR}",
            f"  外部数据目录:      {EXTERNAL_DIR}",
            f"  检索评分:          {'ON' if ENABLE_GRADING else 'OFF'}",
            f"  查询重写:          {'ON' if ENABLE_REWRITE else 'OFF'}",
            f"  混合搜索:          {'ON' if ENABLE_HYBRID_SEARCH else 'OFF'}",
            f"  上下文压缩:        {'ON' if ENABLE_CONTEXT_COMPRESSION else 'OFF'}",
            f"  知识图谱:          {'ON' if ENABLE_GRAPH else 'OFF'}",
            f"  实体抽取:          {'LLM' if ENABLE_GRAPH_LLM_EXTRACTION else 'jieba'}",
        ]
        return "\n".join(lines)

    return f"未知命令。输入 /help 查看可用命令。"


def run_console():
    state = {"agent": None, "messages": [], "session_id": None}
    try:
        state["agent"] = create_rag_agent()
        state["_llm"] = ChatOpenAI(
            model=LLM_MODEL, api_key=DEEPSEEK_API_KEY,
            base_url=DEEPSEEK_API_BASE, temperature=0,
        )
    except Exception as e:
        echo(f"初始化失败: {e}")
        return

    echo(get_status_bar(state))
    echo("")

    while True:
        try:
            line = _get_user_input("你> ")
        except (EOFError, KeyboardInterrupt):
            print()
            if state["messages"]:
                sid = save_history(state["messages"], state["session_id"])
                echo(f"会话已保存: {sid}")
            break

        response = handle_command(line, state)

        if response is None:
            if state["messages"]:
                sid = save_history(state["messages"], state["session_id"])
                echo(f"会话已保存: {sid}")
            break

        if response == "__EXIT__":
            break

        if response:
            echo(response)
            if response.startswith("╔") and "RAG" in response:
                echo("")
            continue

        # Plain text — chat mode
        msgs = state["messages"] + [{"role": "user", "content": line.strip()}]
        echo("助手: ", end="")
        answer_parts = []
        try:
            for chunk in stream_rag_response(state["agent"], msgs):
                if chunk:
                    print(chunk, end="", flush=True)
                    answer_parts.append(chunk)
        except Exception as e:
            print()
            echo(f"  [错误] {e}")
            echo("  API 调用失败，请检查 API Key 和余额")
            continue
        print()
        full_answer = "".join(answer_parts)
        state["messages"].append({"role": "user", "content": line.strip()})
        state["messages"].append({"role": "assistant", "content": full_answer})
        if ENABLE_CONTEXT_COMPRESSION and state.get("_llm"):
            state["messages"] = compress_history(state["messages"], state["_llm"], keep_rounds=10)
