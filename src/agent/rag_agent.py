from deepagents import create_deep_agent
from langchain_openai import ChatOpenAI

from config import DEEPSEEK_API_BASE, DEEPSEEK_API_KEY, LLM_MODEL, ENABLE_HYBRID_SEARCH, ENABLE_GRAPH
from src.agent.tools import retrieve_knowledge, retrieve_graph, set_tool_llm
from src.vector_store.embedding import get_embedding_model
from src.vector_store.chroma_client import get_vector_store

SYSTEM_PROMPT = """你是一个 LangChain 技术助手，基于已有的教程文档回答用户问题。

## 工作方式
1. 当用户提问时，用 retrieve_knowledge 工具搜索知识库获取详细内容（包含文档和知识图谱）
2. 如果检索不到相关信息，诚实回答"不知道"
3. 用中文回答，保持简洁准确
4. 回答时必须引用信息来源，在引用内容后标注 [来源: 文件名.md]

## 可用工具
- retrieve_knowledge: 搜索教程文档和知识图谱（获取详细文档内容 + 实体关系）
"""


def create_rag_agent():
    import os as _os
    _os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"
    import logging
    logging.getLogger("huggingface_hub").setLevel(logging.WARNING)
    logging.getLogger("sentence_transformers").setLevel(logging.WARNING)
    get_embedding_model()
    get_vector_store()

    if ENABLE_HYBRID_SEARCH:
        print("  [BM25] Building keyword index...")
        from src.retrieval.retriever import rebuild_bm25
        rebuild_bm25(get_vector_store())

    model = ChatOpenAI(
        model=LLM_MODEL,
        temperature=0,
        api_key=DEEPSEEK_API_KEY,
        base_url=DEEPSEEK_API_BASE,
    )

    set_tool_llm(model)

    tools = [retrieve_knowledge]
    if ENABLE_GRAPH:
        tools.append(retrieve_graph)

    agent = create_deep_agent(
        model=model,
        tools=tools,
        system_prompt=SYSTEM_PROMPT,
    )
    return agent


def stream_rag_response(agent, messages: list):
    tool_called = False
    for event in agent.stream({"messages": messages}):
        for node_name, value in event.items():
            if not isinstance(value, dict) or "messages" not in value:
                continue
            for msg in value["messages"]:
                mtype = getattr(msg, "type", "")
                content = getattr(msg, "content", "") or ""
                if mtype == "ai" and content:
                    yield content
                elif mtype == "tool" and not tool_called:
                    tool_called = True
                    n = len(content) if content else 0
                    yield f"\n  [知识库检索完成 ({n} 字符)]\n\n"
