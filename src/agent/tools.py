import time
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from hashlib import sha256
from collections import OrderedDict
from pathlib import Path
from threading import Lock

from langchain.tools import tool

from config import (
    TOP_K,
    ENABLE_GRADING,
    ENABLE_REWRITE,
    ENABLE_HYBRID_SEARCH,
    ENABLE_CONTEXT_COMPRESSION,
    ENABLE_GRAPH,
    MAX_CONTEXT_TOKENS,
    RERANK_LLM,
)
from src.retrieval.grading import grade_document
from src.retrieval.rewrite import rewrite_question
from src.llm import get_llm
from src.retrieval.telemetry import RetrievalRecord, retrieval_record_store
from src.application.evidence import evidence_header, source_evidence_note

_TIMING_ENABLED = True
_MAX_CONCURRENT_RERANK = 5
_RETRIEVAL_LOCKS_GUARD = Lock()
_CACHE_KEYS_GUARD = Lock()
_COMPLETED_CACHE_KEYS: OrderedDict[tuple[str, str | None, int], None] = OrderedDict()
_MAX_CACHE_KEYS = 128


def _timing(name: str, t0: float):
    elapsed_ms = (time.perf_counter() - t0) * 1000
    if _TIMING_ENABLED:
        print(f"  [计时] {name}: {elapsed_ms / 1000:.2f}s")
    return round(elapsed_ms, 2)


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
            futures = [
                pool.submit(
                    _compress_document,
                    d.page_content,
                    query,
                    llm,
                    str((getattr(d, "metadata", {}) or {}).get("source", "unknown")),
                )
                for d in docs
            ]
            compressed = [fut.result() for fut in futures]
        results = []
        for doc, summary in zip(docs, compressed):
            source = doc.metadata.get("source", "unknown")
            results.append(f"{evidence_header(source)}\n{summary}")
        return "\n\n---\n\n".join(results)
    results = []
    for doc in docs:
        source = doc.metadata.get("source", "unknown")
        content = doc.page_content
        if len(content) > MAX_CONTEXT_TOKENS * 4:
            content = content[:MAX_CONTEXT_TOKENS * 4] + "..."
        results.append(f"{evidence_header(source)}\n{content}")
    return "\n\n---\n\n".join(results)


def _index_version() -> int:
    try:
        from src.resources import ResourceManager
        return ResourceManager.get_instance().get_index_version()
    except Exception:
        return 0


def _cache_key_completed(key: tuple[str, str | None, int]) -> bool:
    with _CACHE_KEYS_GUARD:
        return key in _COMPLETED_CACHE_KEYS


def _mark_cache_key_completed(key: tuple[str, str | None, int]) -> None:
    with _CACHE_KEYS_GUARD:
        _COMPLETED_CACHE_KEYS[key] = None
        _COMPLETED_CACHE_KEYS.move_to_end(key)
        while len(_COMPLETED_CACHE_KEYS) > _MAX_CACHE_KEYS:
            _COMPLETED_CACHE_KEYS.popitem(last=False)


@lru_cache(maxsize=128)
def _retrieve_knowledge_cached(query: str, capability: str | None, index_version: int) -> str:
    """Cache the expensive retrieve/rerank/compress result until the index changes."""
    started = time.perf_counter()
    record = RetrievalRecord(
        query=query,
        capability=capability,
        index_version=index_version,
        flags={
            "grading": ENABLE_GRADING,
            "rewrite": ENABLE_REWRITE,
            "hybrid_search": ENABLE_HYBRID_SEARCH,
            "context_compression": ENABLE_CONTEXT_COMPRESSION,
            "graph": ENABLE_GRAPH,
        },
    )
    try:
        llm = _get_rerank_llm() if (ENABLE_GRADING or ENABLE_CONTEXT_COMPRESSION) else None

        fetch_k = TOP_K * 3 if ENABLE_GRADING else TOP_K
        _t0 = time.perf_counter()
        raw_docs = _search(query, fetch_k, capability=capability)
        record.stages["search_ms"] = _timing("混合检索 (vector+BM25)", _t0)
        record.raw_docs_count = len(raw_docs or [])

        _t0 = time.perf_counter()
        docs = _grade(query, raw_docs, llm) if raw_docs else []
        record.stages["grading_ms"] = _timing("文档评分", _t0)
        record.selected_docs_count = len(docs or [])

        _t0 = time.perf_counter()
        result = _compress(docs, query, llm) if docs else ""
        record.stages["compression_ms"] = _timing("上下文压缩", _t0)

        if ENABLE_GRAPH:
            try:
                from src.application.knowledge import retrieve_graph
                _t0 = time.perf_counter()
                graph_result = retrieve_graph(query)
                record.stages["graph_ms"] = _timing("知识图谱检索", _t0)
                if graph_result != "未找到相关的图谱信息。":
                    result += f"\n\n【知识图谱关联】\n{graph_result}"
            except Exception as e:
                record.error = f"graph: {e}"
                print(f"  [图谱] 检索失败: {e}")

        record.finish((time.perf_counter() - started) * 1000)
        _mark_cache_key_completed((query, capability, index_version))
        _timing("retrieve_knowledge 工具总计", started)
        return result if result else "未找到相关信息。"
    except Exception as exc:
        record.error = str(exc)
        record.finish((time.perf_counter() - started) * 1000, status="failed")
        raise
    finally:
        retrieval_record_store.put(record)


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
    with _CACHE_KEYS_GUARD:
        _COMPLETED_CACHE_KEYS.clear()


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
    key = (normalized, capability, index_version)
    with _get_retrieval_lock(normalized, capability, index_version):
        started = time.perf_counter()
        cache_hit = _cache_key_completed(key)
        result = _retrieve_knowledge_cached(normalized, capability, index_version)
        if cache_hit:
            record = RetrievalRecord(
                query=normalized,
                capability=capability,
                index_version=index_version,
                cache_hit=True,
                flags={
                    "grading": ENABLE_GRADING,
                    "rewrite": ENABLE_REWRITE,
                    "hybrid_search": ENABLE_HYBRID_SEARCH,
                    "context_compression": ENABLE_CONTEXT_COMPRESSION,
                    "graph": ENABLE_GRAPH,
                },
            )
            record.finish((time.perf_counter() - started) * 1000)
            retrieval_record_store.put(record)
        return result


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

    started = time.perf_counter()
    source_id = sha256((title + "\n" + content).encode("utf-8")).hexdigest()[:16]
    from config import EXTERNAL_DIR
    target = Path(EXTERNAL_DIR) / f"research_{source_id}.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    source_block = f"\n\n## 参考来源\n{sources.strip()}" if sources.strip() else ""
    target.write_text(f"# {title}\n\n{content}{source_block}\n", encoding="utf-8")

    _t_index = time.perf_counter()
    from src.ingestion.pipeline import run_add_path
    chunks = run_add_path(str(target), external_dir=str(Path(EXTERNAL_DIR)), echo_fn=print)
    _timing("网页内容入库", _t_index)
    return f"已将研究资料加入知识库：{title}（{chunks} 个片段，总耗时 {time.perf_counter() - started:.2f}s）"


def _compress_document(text: str, query: str, llm, source: str = "unknown") -> str:
    prompt = (
        "你是一个文档压缩助手。根据用户问题，从以下文档中提取最关键的信息，"
        "保留原文明确记载的事实、数据、代码和关键结论，去掉冗余内容，输出精简摘要（100-150字）。"
        "不得从算子名、变量名、参数位置或代码调用推断原文未写出的参数语义、输出类型或适用范围。"
        "若证据类型为示例代码，只摘录可直接观察到的调用，并明确其不是参数文档。\n\n"
        f"来源: {source}\n"
        f"{source_evidence_note(source)}\n\n"
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
