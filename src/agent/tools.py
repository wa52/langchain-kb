import time
from concurrent.futures import ThreadPoolExecutor

from langchain.tools import tool

from config import TOP_K, ENABLE_GRADING, ENABLE_REWRITE, ENABLE_CONTEXT_COMPRESSION, ENABLE_GRAPH, MAX_CONTEXT_TOKENS, RERANK_LLM
from src.retrieval.grading import grade_document
from src.retrieval.rewrite import rewrite_question
from src.llm import get_llm

_TIMING_ENABLED = True
_MAX_CONCURRENT_RERANK = 5


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
    from src.vector_store.service import VectorStoreService
    retriever = VectorStoreService().get_retriever(k=k, capability=capability)
    return retriever.invoke(query)


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


@tool
def retrieve_knowledge(query: str, capability: str | None = None) -> str:
    """搜索知识库中与问题最相关的内容。capability 可选能力域编号（1-7），用于限定检索范围。当你需要从已有的知识库文档中查找信息时使用此工具。"""
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
            from src.graph_store.service import GraphService
            _t0 = time.time()
            graph_result = GraphService().search(query)
            _timing("知识图谱检索", _t0)
            if graph_result != "未找到相关的图谱信息。":
                result += f"\n\n【知识图谱关联】\n{graph_result}"
        except Exception as e:
            print(f"  [图谱] 检索失败: {e}")

    _timing("retrieve_knowledge 工具总计", _t_all)
    return result if result else "未找到相关信息。"


@tool
def retrieve_graph(query: str) -> str:
    """搜索知识图谱中与问题相关的实体和关系。当你想了解某个概念或实体之间的关联关系时使用此工具。"""
    from src.graph_store.service import GraphService
    return GraphService().search(query)


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
