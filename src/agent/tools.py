import time
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from hashlib import sha256
from pathlib import Path
from threading import Lock

from langchain.tools import tool

from config import TOP_K, ENABLE_GRADING, ENABLE_REWRITE, ENABLE_CONTEXT_COMPRESSION, ENABLE_GRAPH, MAX_CONTEXT_TOKENS, RERANK_LLM
from src.retrieval.grading import grade_document
from src.retrieval.rewrite import rewrite_question
from src.llm import get_llm

_TIMING_ENABLED = True
_MAX_CONCURRENT_RERANK = 5
_RETRIEVAL_LOCKS_GUARD = Lock()


def _timing(name: str, t0: float):
    if _TIMING_ENABLED:
        print(f"  [计时] {name}: {time.time() - t0:.2f}s")


def _get_rerank_llm():
    """评分/压缩使用的 LLM：按 RERANK_LLM 配置选择云端或本地。"""
    if RERANK_LLM == "local":
        from src.llm.client import get_local_llm
        return get_local_llm(temperature=0)
    return get_llm(temperature=0)


def _search(query, k, capability=None):
    from src.application.knowledge import retrieve_documents
    return retrieve_documents(query, k, capability=capability)


def _grade_parallel(query, docs, llm):
    """并发调用 grade_document，返回按原顺序过滤后的相关文档。"""
    if not docs:
        return []
    workers = min(_MAX_CONCURRENT_RERANK, len(docs))
    relevant = []
    try:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(grade_document, query, d.page_content, llm) for d in docs]
            for doc, fut in zip(docs, futures):
                if fut.result():
                    relevant.append(doc)
    except Exception as e:
        print(f"  [评分] 评分异常: {e}，返回原始结果")
        return None
    return relevant


def _grade(query, docs, llm):
    if not (ENABLE_GRADING and llm):
        return docs[:TOP_K]
    relevant = _grade_parallel(query, docs, llm)
    if relevant is None:
        return docs[:TOP_K]
    if not relevant and ENABLE_REWRITE:
        print("  [评分] 全部不相关，尝试改写查询...")
        new_query = rewrite_question(query, llm)
        if new_query and new_query != query:
            fetch_k = TOP_K * 3
            raw_docs = _search(new_query, fetch_k)
            relevant = _grade_parallel(query, raw_docs, llm) or []
    return relevant[:TOP_K] if relevant else docs[:TOP_K]


def _compress(docs, query, llm):
    if not docs:
        return "未找到相关信息。"
    if ENABLE_CONTEXT_COMPRESSION and llm:
        workers = min(_MAX_CONCURRENT_RERANK, len(docs))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(_compress_document, d.page_content, query, llm) for d in docs]
            compressed = [fut.result() for fut in futures]
        results = []
        for doc, summary in zip(docs, compressed):
            source = doc.metadata.get("source", "unknown")
            results.append(f"[来源: {source}]\n{summary}")
        return "\n\n---\n\n".join(results)
    results = []
    for doc in docs:
        source = doc.metadata.get("source", "unknown")
        content = doc.page_content
        if len(content) > MAX_CONTEXT_TOKENS * 4:
            content = content[:MAX_CONTEXT_TOKENS * 4] + "..."
        results.append(f"[来源: {source}]\n{content}")
    return "\n\n---\n\n".join(results)


def _index_version() -> int:
    try:
        from src.resources import ResourceManager
        return ResourceManager.get_instance().get_index_version()
    except Exception:
        return 0


@lru_cache(maxsize=128)
def _retrieve_knowledge_cached(query: str, capability: str | None, index_version: int) -> str:
    """Cache the expensive retrieve/rerank/compress result until the index changes."""
    _t_all = time.time()
    llm = _get_rerank_llm() if (ENABLE_GRADING or ENABLE_CONTEXT_COMPRESSION) else None

    fetch_k = TOP_K * 3 if ENABLE_GRADING else TOP_K
    _t0 = time.time()
    raw_docs = _search(query, fetch_k, capability=capability)
    _timing("混合检索 (vector+BM25)", _t0)
    _t0 = time.time()
    docs = _grade(query, raw_docs, llm) if raw_docs else []
    _timing("文档评分", _t0)
    _t0 = time.time()
    result = _compress(docs, query, llm) if docs else ""
    _timing("上下文压缩", _t0)

    if ENABLE_GRAPH:
        try:
            from src.application.knowledge import retrieve_graph
            _t0 = time.time()
            graph_result = retrieve_graph(query)
            _timing("知识图谱检索", _t0)
            if graph_result != "未找到相关的图谱信息。":
                result += f"\n\n【知识图谱关联】\n{graph_result}"
        except Exception as e:
            print(f"  [图谱] 检索失败: {e}")

    _timing("retrieve_knowledge 工具总计", _t_all)
    return result if result else "未找到相关信息。"


@lru_cache(maxsize=256)
def _retrieval_lock(query: str, capability: str | None, index_version: int) -> Lock:
    """Return a per-query lock so concurrent cache misses collapse into one run."""
    return Lock()


def _get_retrieval_lock(query: str, capability: str | None, index_version: int) -> Lock:
    # functools.lru_cache may execute the wrapped factory twice on concurrent
    # misses, so serialize lock creation itself.
    with _RETRIEVAL_LOCKS_GUARD:
        return _retrieval_lock(query, capability, index_version)


def clear_retrieval_cache() -> None:
    """Drop cached evidence after indexing or configuration changes."""
    _retrieve_knowledge_cached.cache_clear()


@tool
def retrieve_knowledge(query: str, capability: str | None = None) -> str:
    """检索本地知识库，适用于需要文档事实、来源、工业视觉技术或项目经验的问题。

    不要用于寒暄、通用写作、翻译或仅依赖用户已提供内容的任务。
    query 应是精炼且可独立理解的检索问题；capability 可选能力域编号 1-7。
    返回带 `[来源: 文件名]` 的证据片段；相同查询会复用缓存，索引更新后自动失效。
    """
    normalized = " ".join(query.strip().split())
    if not normalized:
        return "未找到相关信息。"
    index_version = _index_version()
    with _get_retrieval_lock(normalized, capability, index_version):
        return _retrieve_knowledge_cached(normalized, capability, index_version)


@tool
def retrieve_graph(query: str) -> str:
    """查询知识图谱中的实体关系，仅用于概念关联、依赖链或上下游关系问题。

    普通文档问答不要调用本工具，应优先使用 retrieve_knowledge。
    """
    from src.application.knowledge import retrieve_graph as search_graph
    return search_graph(query)


@tool
def save_research_material(title: str, content: str, sources: str = "") -> str:
    """保存联网检索后整理出的研究资料，并加入知识库。

    先用 browser MCP 搜索和阅读公开资料，再把去重、核实后的结论传入本工具；
    不会把未经整理的网页 HTML 直接写入知识库。
    """
    title = title.strip()
    content = content.strip()
    if len(title) < 2 or len(content) < 80:
        return "无法入库：标题至少 2 个字符，整理后的资料至少 80 个字符。"
    if len(content) > 200_000:
        return "无法入库：整理后的资料超过 200 KB 限制。"

    started = time.time()
    source_id = sha256((title + "\n" + content).encode("utf-8")).hexdigest()[:16]
    from config import EXTERNAL_DIR
    target = Path(EXTERNAL_DIR) / f"research_{source_id}.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    source_block = f"\n\n## 参考来源\n{sources.strip()}" if sources.strip() else ""
    target.write_text(f"# {title}\n\n{content}{source_block}\n", encoding="utf-8")

    _t_index = time.time()
    from src.ingestion.pipeline import run_add_path
    chunks = run_add_path(str(target), external_dir=str(Path(EXTERNAL_DIR)), echo_fn=print)
    _timing("网页内容入库", _t_index)
    return f"已将研究资料加入知识库：{title}（{chunks} 个片段，总耗时 {time.time() - started:.2f}s）"


def _compress_document(text: str, query: str, llm) -> str:
    prompt = (
        "你是一个文档压缩助手。根据用户问题，从以下文档中提取最关键的信息，"
        "保留事实、数据、代码和关键结论，去掉冗余内容，输出精简摘要（100-150字）。\n\n"
        f"问题: {query}\n\n"
        f"文档: {text[:1500]}\n\n"
        "摘要:"
    )
    try:
        response = llm.invoke(prompt)
        content = response.content.strip()
        return content if content else text[:300]
    except Exception:
        return text[:300]
