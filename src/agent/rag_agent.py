from deepagents import create_deep_agent

from config import ENABLE_HYBRID_SEARCH, ENABLE_GRAPH, PRODUCT_NAME
from src.agent.tools import retrieve_knowledge, retrieve_graph, save_research_material
from src.agent.project_workflow import project_workflow, build_workflow_prompt
from src.vector_store.embedding import get_embedding_model
from src.vector_store.service import VectorStoreService
from src.vector_store.chroma_client import get_vector_store
from src.llm import get_llm

SYSTEM_PROMPT = f"""你是一个{PRODUCT_NAME}工业视觉 AI 工程师，负责基于知识库回答工业视觉项目相关的问题，并能引导用户完成完整的工业视觉项目。除非用户直接询问，否则不要主动说明你使用了什么底层模型，也不要自称 Claude、GPT 或其他特定模型。

## 工作方式
1. 当用户提问时，先用 retrieve_knowledge 工具搜索知识库获取相关内容（文档片段 + 知识图谱）
2. 当用户描述一个工业视觉项目时，用 project_workflow 工具按阶段引导项目推进
3. 优先依据检索到的内容回答，保持简洁准确
4. 如果知识库中没有与问题相关的信息，如实说明"知识库中没有找到相关信息"，不要编造或猜测
5. 回答时标注信息来源，在引用内容后标注 [来源: 文件名]
6. 用中文回答
7. 用户要求联网查资料时，先用 browser MCP 搜索并阅读多个公开来源，整理去重、核实事实后调用 save_research_material 入库，最后重新检索并回答
8. 只能声称实际工具列表中存在的工具；工具调用失败时说明当前能力不可用，不要声称已经完成未成功的操作

## 项目引导
{build_workflow_prompt()}

## 可用工具
- retrieve_knowledge: 搜索知识库中的文档和知识图谱，获取与问题最相关的内容
- project_workflow: 按工业视觉项目阶段（需求分析→知识研究→方案设计→算法实现→工程开发→项目验证）引导项目推进
- save_research_material: 将联网检索后整理好的研究资料和来源加入知识库
"""


def create_rag_agent():
    import os as _os
    import time as _time
    from src.status import get_registry
    get_registry().set_loading("agent", "构建 RAG Agent")
    _os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"
    import logging
    logging.getLogger("huggingface_hub").setLevel(logging.WARNING)
    logging.getLogger("sentence_transformers").setLevel(logging.WARNING)

    _t0 = _time.time()
    get_embedding_model()
    print(f"  [计时] 加载 embedding 模型: {_time.time() - _t0:.2f}s")

    _t1 = _time.time()
    get_vector_store()
    print(f"  [计时] 连接向量库: {_time.time() - _t1:.2f}s")

    if ENABLE_HYBRID_SEARCH:
        _t2 = _time.time()
        VectorStoreService().rebuild_bm25()
        print(f"  [计时] 构建/加载 BM25 索引: {_time.time() - _t2:.2f}s")

    _t3 = _time.time()
    model = get_llm(temperature=0)
    print(f"  [计时] 初始化 LLM: {_time.time() - _t3:.2f}s")

    tools = [retrieve_knowledge, project_workflow, save_research_material]
    if ENABLE_GRAPH:
        tools.append(retrieve_graph)

    # Load external MCP tools (opencode-style mcp.json). Degrades gracefully:
    # a failure here never blocks the local knowledge tools.
    external_names: list[str] = []
    try:
        from src.agent.mcp_client import load_mcp_tools, default_mcp_config_path
        external = load_mcp_tools(default_mcp_config_path())
        if external:
            tools.extend(external)
            external_names = [getattr(t, "name", "external") for t in external]
            print(f"  [MCP] 已加载 {len(external)} 个外部工具")
    except Exception as e:
        print(f"  [MCP] 外部工具加载失败（不影响本地工具）: {e}")

    _t4 = _time.time()
    prompt = SYSTEM_PROMPT
    if external_names:
        prompt += "\n\n## 当前已加载的外部 MCP\n- " + "\n- ".join(external_names)
    else:
        prompt += "\n\n当前没有成功加载外部 MCP；不要声称可以联网或使用浏览器。"
    agent = create_deep_agent(
        model=model,
        tools=tools,
        system_prompt=prompt,
    )
    get_registry().set_ready("agent", "Deep Agent")
    print(f"  [计时] 构建 Deep Agent: {_time.time() - _t4:.2f}s")
    return agent


def stream_rag_response(agent, messages: list, on_tool=None):
    def content_length(value) -> int:
        if isinstance(value, str):
            return len(value)
        if isinstance(value, list):
            total = 0
            for item in value:
                if isinstance(item, dict):
                    total += len(str(item.get("text", item.get("content", ""))))
                else:
                    total += len(str(getattr(item, "text", item)))
            return total
        return len(str(value)) if value else 0

    tool_called = False
    seen_tool_ids = set()
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
                    n = content_length(content)
                    yield f"\n  [知识库检索完成 ({n} 字符)]\n\n"
                if on_tool is not None and mtype == "tool":
                    tid = getattr(msg, "tool_call_id", None) or getattr(msg, "id", None)
                    if tid is not None and tid in seen_tool_ids:
                        continue
                    if tid is not None:
                        seen_tool_ids.add(tid)
                    on_tool(getattr(msg, "name", "") or "tool")
