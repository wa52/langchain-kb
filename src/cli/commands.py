import os
from pathlib import Path

import click
from dotenv import set_key

from config import DATA_DIR, EXTERNAL_DIR, CHUNK_SIZE, CHUNK_OVERLAP, TOP_K, EMBEDDING_MODEL, LLM_MODEL, ENABLE_GRADING, ENABLE_REWRITE, ENABLE_HYBRID_SEARCH, ENABLE_CONTEXT_COMPRESSION, ENABLE_GRAPH, ENABLE_GRAPH_LLM_EXTRACTION, MAX_CONTEXT_TOKENS, PRODUCT_NAME
from src.ingestion.pipeline import run_ingestion, run_incremental_update, run_single_file_update, run_add_path, run_remove, run_rebuild


def echo(msg: str = "", end: str = "\n"):
    try:
        print(msg, end=end, flush=True)
    except UnicodeEncodeError:
        safe = str(msg).encode("utf-8", errors="replace").decode("utf-8", errors="replace")
        print(safe, end=end, flush=True)


@click.group()
def cli():
    pass


@cli.command()
@click.option("--chunk-size", default=None, type=int, help="Chunk size")
@click.option("--chunk-overlap", default=None, type=int, help="Chunk overlap")
def ingest(chunk_size, chunk_overlap):
    """全量导入 DATA_DIR 文档到向量数据库"""
    kwargs = {}
    if chunk_size:
        kwargs["chunk_size"] = chunk_size
    if chunk_overlap:
        kwargs["chunk_overlap"] = chunk_overlap
    count = run_ingestion(DATA_DIR, echo_fn=echo, **kwargs)
    echo(f"==> 成功导入 {count} 个文档片段")


@cli.command()
def update():
    """增量更新：扫描 DATA_DIR + data/external/ 的变更文件"""
    count = run_incremental_update(str(DATA_DIR), EXTERNAL_DIR, echo_fn=echo)
    echo(f"==> 增量更新完成，处理了 {count} 个片段")


@cli.command()
@click.argument("filepath")
def update_file(filepath):
    """更新单个文件"""
    count = run_single_file_update(filepath, echo_fn=echo)
    echo(f"==> 文件更新完成，处理了 {count} 个片段")


@cli.command()
def rebuild():
    """重建向量索引（清空后重新导入 DATA_DIR + data/external/）"""
    confirm = click.confirm("这将清空现有数据库，确定继续？")
    if not confirm:
        return
    run_rebuild(DATA_DIR, echo_fn=echo)
    echo("==> 索引重建完成")


@cli.command()
@click.argument("path")
def add(path):
    """添加外部文件或目录到知识库（自动复制到 data/external/）"""
    count = run_add_path(path, EXTERNAL_DIR, echo_fn=echo)
    echo(f"==> 成功添加 {count} 个文档片段")


@cli.command()
def list_files():
    """列出知识库中的所有文件"""
    from src.ingestion.tracker import list_all_files
    files = list_all_files()
    if not files:
        echo("暂无文件记录")
        return
    echo(f"{'来源':<8} {'文件':<30}")
    echo(f"{'----':<8} {'----':<30}")
    for f in sorted(files, key=lambda x: (x["source_type"], x["file_key"])):
        label = "内部" if f["source_type"] == "internal" else "外部"
        echo(f"{label:<8} {f['file_key']:<30}")


@cli.command()
@click.argument("name")
@click.option("--keep-file", is_flag=True, help="保留文件，仅从向量库删除")
def remove(name, keep_file):
    """从知识库移除某个文件"""
    run_remove(name, EXTERNAL_DIR, keep_file=keep_file, echo_fn=echo)


@cli.command()
@click.argument("query")
def search(query):
    """检索知识库（不调用 LLM，仅搜索）"""
    from src.vector_store.service import VectorStoreService
    retriever = VectorStoreService().get_retriever()
    docs = retriever.invoke(query)
    if not docs:
        echo("未找到相关文档")
        return
    echo(f"找到 {len(docs)} 条结果:\n")
    for i, doc in enumerate(docs, 1):
        source = doc.metadata.get("source", "unknown")
        text = doc.page_content[:300]
        echo(f"[{i}] ({source})")
        echo(text)
        echo("")


@cli.command()
@click.option("--session", default=None, help="恢复指定会话ID")
@click.option("--list-sessions", "list_only", is_flag=True, help="列出历史会话")
def chat(session, list_only):
    """交互式问答（多轮对话，流式输出）"""
    from src.agent.rag_agent import create_rag_agent, stream_rag_response
    from src.agent.chat_history import save_history, load_history, list_sessions, compress_history
    from src.llm import get_llm
    _chat_llm = get_llm(temperature=0)

    if list_only:
        sessions = list_sessions()
        if not sessions:
            echo("暂无历史会话")
            return
        echo(f"{'会话ID':<25} {'时间':<16} {'轮':<3} {'标题':<24}")
        echo("-" * 70)
        for s in sessions:
            title = s.get("title", "空会话")
            echo(f"{s['id']:<25} {s['created']:<16} {s['turns']:<3} {title:<24}")
        return

    agent = create_rag_agent()
    raw_history = []
    session_id = session

    if session_id:
        saved = load_history(session_id)
        if saved is None:
            echo(f"未找到会话: {session_id}")
            return
        raw_history = saved
        n_turns = len([m for m in raw_history if m["role"] == "user"])
        echo(f"已恢复会话 ({n_turns} 轮对话)\n")

    echo("=" * 40)
    echo(f"  {PRODUCT_NAME} — 交互问答")
    echo("=" * 40)
    echo("输入问题开始对话，输入 exit 退出\n")

    while True:
        query = click.prompt("你", prompt_suffix="> ")
        if query.lower() in ("exit", "quit"):
            if raw_history:
                session_id = save_history(raw_history, session_id)
                echo(f"会话已保存: {session_id}")
            echo("再见！")
            break
        if query.lower() == "save":
            session_id = save_history(raw_history, session_id)
            echo(f"会话已保存: {session_id}")
            echo("再见！")
            break
        if query.lower() == "clear":
            raw_history.clear()
            session_id = None
            echo("对话历史已清除")
            continue

        messages = raw_history + [{"role": "user", "content": query}]
        echo("助手: ")
        answer_parts = []
        try:
            for chunk in stream_rag_response(agent, messages):
                if chunk:
                    print(chunk, end="", flush=True)
                    answer_parts.append(chunk)
        except Exception as e:
            print()
            echo(f"  [错误] {e}")
            echo("  API调用失败，请检查 API Key 和余额")
            continue
        print("\n")
        full_answer = "".join(answer_parts)
        raw_history.append({"role": "user", "content": query})
        raw_history.append({"role": "assistant", "content": full_answer})
        if ENABLE_CONTEXT_COMPRESSION:
            raw_history = compress_history(raw_history, _chat_llm, keep_rounds=10)


@cli.command()
def stats():
    """显示知识库详细信息"""
    from src.vector_store.service import VectorStoreService
    from src.ingestion.tracker import list_all_files

    stats = VectorStoreService().get_stats()
    echo("=" * 40)
    echo("知识库统计")
    echo("=" * 40)
    echo(f"  向量总数:        {stats['count']}")
    echo(f"  来源文件数:      {stats['source_count']}")

    files = list_all_files()
    int_cnt = len([f for f in files if f["source_type"] == "internal"])
    ext_cnt = len([f for f in files if f["source_type"] == "external"])
    echo(f"  内部文件:        {int_cnt}")
    echo(f"  外部文件:        {ext_cnt}")

    if stats["sources"]:
        echo(f"  ── 来源文件列表 ──")
        for s in stats["sources"][:30]:
            echo(f"    {s}")
        if len(stats["sources"]) > 30:
            echo(f"    ... 还有 {len(stats['sources']) - 30} 个文件")

    echo("")


@cli.command()
@click.argument("query")
def graph_search(query):
    """搜索知识图谱"""
    from src.graph_store.service import GraphService
    result = GraphService().search(query)
    echo(result)


@cli.command()
def build_graph():
    """从文档构建知识图谱"""
    from src.graph_store.service import GraphService
    echo("构建知识图谱...")
    kg = GraphService().build_from_disk()
    st = kg.stats()
    echo(f"==> 知识图谱构建完成: {st['entities']} 实体, {st['relations']} 关系")
    echo(f"    实体类型: {st['types']}")


@cli.command()
@click.argument("mode", type=click.Choice(["llm", "jieba"]), required=False)
def mode(mode):
    """设置图谱实体抽取模式 (llm/jieba)。不传参数时显示当前模式。"""
    import config as cfg
    if mode is None:
        current = "LLM" if cfg.ENABLE_GRAPH_LLM_EXTRACTION else "jieba"
        echo(f"当前抽取模式: {current}")
        return
    dotenv_path = Path(cfg.KNOWLEDGE_HOME) / ".env"
    dotenv_path.parent.mkdir(parents=True, exist_ok=True)
    dotenv_path.touch(exist_ok=True)
    is_llm = mode == "llm"
    set_key(str(dotenv_path), "ENABLE_GRAPH_LLM_EXTRACTION", "true" if is_llm else "false")
    os.environ["ENABLE_GRAPH_LLM_EXTRACTION"] = "true" if is_llm else "false"
    cfg.ENABLE_GRAPH_LLM_EXTRACTION = is_llm
    echo(f"切换到 {mode.upper()} 抽取模式（立即生效）")


@cli.command()
def config():
    """显示当前配置"""
    echo("=" * 40)
    echo("当前配置")
    echo("=" * 40)
    echo(f"  数据目录:          {DATA_DIR}")
    echo(f"  外部数据目录:      {EXTERNAL_DIR}")
    echo(f"  Embedding模型:     {EMBEDDING_MODEL}")
    echo(f"  LLM模型:           {LLM_MODEL}")
    echo(f"  Chunk大小:         {CHUNK_SIZE}")
    echo(f"  Chunk重叠:         {CHUNK_OVERLAP}")
    echo(f"  检索数量(TOP_K):   {TOP_K}")
    echo(f"  检索评分:          {'ON' if ENABLE_GRADING else 'OFF'}")
    echo(f"  查询重写:          {'ON' if ENABLE_REWRITE else 'OFF'}")
    echo(f"  混合搜索:          {'ON' if ENABLE_HYBRID_SEARCH else 'OFF'}")
    echo(f"  上下文压缩:        {'ON' if ENABLE_CONTEXT_COMPRESSION else 'OFF'}")
    echo(f"  知识图谱:          {'ON' if ENABLE_GRAPH else 'OFF'}")
    echo(f"  实体抽取:          {'LLM' if ENABLE_GRAPH_LLM_EXTRACTION else 'jieba'}")
    echo(f"  最大上下文Token:   {MAX_CONTEXT_TOKENS}")
    echo(f"  向量数据库:        chroma_db/")
    echo("")
