from langchain.tools import tool

from config import TOP_K, ENABLE_GRADING, ENABLE_REWRITE, ENABLE_CONTEXT_COMPRESSION, ENABLE_GRAPH, MAX_CONTEXT_TOKENS
from src.retrieval.grading import grade_document
from src.retrieval.rewrite import rewrite_question
from src.llm import get_llm


def _search(query, k):
    from src.vector_store.service import VectorStoreService
    retriever = VectorStoreService().get_retriever(k=k)
    return retriever.invoke(query)


def _grade(query, docs, llm):
    if not (ENABLE_GRADING and llm):
        return docs[:TOP_K]
    relevant = []
    try:
        for doc in docs:
            if grade_document(query, doc.page_content, llm):
                relevant.append(doc)
    except Exception as e:
        print(f"  [评分] 评分异常: {e}，返回原始结果")
        return docs[:TOP_K]
    if not relevant and ENABLE_REWRITE:
        print("  [评分] 全部不相关，尝试改写查询...")
        new_query = rewrite_question(query, llm)
        if new_query and new_query != query:
            fetch_k = TOP_K * 3
            raw_docs = _search(new_query, fetch_k)
            try:
                relevant = [d for d in raw_docs if grade_document(query, d.page_content, llm)]
            except Exception as e:
                print(f"  [评分] 重试评分异常: {e}")
                relevant = []
    return relevant[:TOP_K] if relevant else docs[:TOP_K]


def _compress(docs, query, llm):
    if not docs:
        return "未找到相关信息。"
    if ENABLE_CONTEXT_COMPRESSION and llm:
        compressed = []
        for doc in docs:
            summary = _compress_document(doc.page_content, query, llm)
            compressed.append(summary)
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
def retrieve_knowledge(query: str) -> str:
    """搜索知识库中与问题最相关的内容。当你需要从已有的知识库文档中查找信息时使用此工具。"""
    llm = get_llm(temperature=0) if (ENABLE_GRADING or ENABLE_CONTEXT_COMPRESSION) else None

    fetch_k = TOP_K * 3 if ENABLE_GRADING else TOP_K
    raw_docs = _search(query, fetch_k)
    docs = _grade(query, raw_docs, llm) if raw_docs else []
    result = _compress(docs, query, llm) if docs else ""

    if ENABLE_GRAPH:
        try:
            from src.graph_store.service import GraphService
            graph_result = GraphService().search(query)
            if graph_result != "未找到相关的图谱信息。":
                result += f"\n\n【知识图谱关联】\n{graph_result}"
        except Exception as e:
            print(f"  [图谱] 检索失败: {e}")

    return result if result else "未找到相关信息。"


@tool
def retrieve_graph(query: str) -> str:
    """搜索知识图谱中与问题相关的实体和关系。当你想了解某个概念或实体之间的关联关系时使用此工具。"""
    from src.graph_store.service import GraphService
    return GraphService().search(query)


def _compress_document(text: str, query: str, llm) -> str:
    prompt = (
        "你是一个文档压缩助手。根据用户问题，从以下文档中提取最关键的信息。\n"
        "保留事实、数据、代码和关键结论，去掉冗余内容。\n"
        "输出精简摘要（100-150字）。\n\n"
        f"问题: {query}\n\n"
        f"文档: {text[:1500]}\n\n"
        "摘要:"
    )
    try:
        response = llm.invoke(prompt)
        return response.content.strip()
    except Exception:
        return text[:300]
