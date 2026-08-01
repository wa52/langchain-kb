"""Stage 4: generate an initial industrial-vision solution from a requirement.

Retrieves capability-scoped knowledge (cap 1,3,4,5,6), then one LLM call
assembles a standard 10-section solution following a project template.
"""

from src.capability.model import CAPABILITY_DOMAINS


def _search_capability(capability: int, query: str, k: int = 5) -> list[dict]:
    """Retrieve knowledge for a capability domain (real vector search)."""
    from src.vector_store.service import VectorStoreService
    retriever = VectorStoreService().get_retriever(k=k, capability=str(capability))
    docs = retriever.invoke(query)
    return [
        {"source": d.metadata.get("source", "unknown"),
         "content": d.page_content[:500]}
        for d in docs
    ]


# 10 standard sections (matching knowledge/templates/*.md)
SOLUTION_SECTIONS = [
    ("requirement", "需求分析"),
    ("target", "检测目标"),
    ("spec", "技术指标"),
    ("imaging", "成像方案"),
    ("positioning", "定位方案"),
    ("vision_flow", "视觉流程"),
    ("algorithm", "算法选择"),
    ("architecture", "软件架构建议"),
    ("risk", "风险分析"),
    ("questions", "待确认问题"),
]

# Which capability feeds each section
_SECTION_CAPABILITY = {
    "requirement": 1,
    "target": 1,
    "spec": 1,
    "imaging": 3,
    "positioning": 3,
    "vision_flow": 4,
    "algorithm": 4,
    "architecture": 5,
    "risk": 6,
    "questions": 1,
}

_GENERATE_PROMPT = """你是一名工业视觉 AI 工程师。请为以下项目需求生成一份结构化的初版工业视觉方案。

## 项目需求
{requirement}

## 检测任务与算法建议
{algorithm}

## 知识参考（来自知识库，按能力域检索）
{knowledge}

## 输出要求
- 按以下 10 个章节组织方案，每章节给出要点说明，用中文
- 依据知识库内容给出具体建议（成像、算法、软件），不要编造
- 每章节后标注参考来源 [来源: 文件名]（如有）

章节:
1. 需求分析
2. 检测目标
3. 技术指标
4. 成像方案
5. 定位方案
6. 视觉流程
7. 算法选择
8. 软件架构建议
9. 风险分析
10. 待确认问题
"""


def _render_requirement(requirement: dict) -> str:
    lines = []
    for k, v in requirement.items():
        if k == "unknown":
            continue
        if v:
            lines.append(f"- {k}: {v}")
    if requirement.get("unknown"):
        lines.append(f"- 未明确: {', '.join(requirement['unknown'])}")
    return "\n".join(lines) or "- （未提供）"


def _render_knowledge(knowledge_map: dict) -> str:
    lines = []
    for cap, refs in knowledge_map.items():
        dom = next((d["name"] for d in CAPABILITY_DOMAINS if d["id"] == cap), str(cap))
        if not refs:
            continue
        lines.append(f"\n### 能力域 {cap}（{dom}）")
        for r in refs[:3]:
            lines.append(f"- [{r['source']}] {r['content'][:200]}")
    return "\n".join(lines)


def generate_solution(requirement: dict, algorithm: dict, llm) -> dict:
    """Assemble a 10-section solution from requirement + algorithm + knowledge.

    One LLM call fills content; knowledge is retrieved per capability domain.
    Returns a dict with 'sections' (list of {key, title, content}) and meta.
    """
    # Retrieve per-capability knowledge for each section
    knowledge_map: dict[int, list[dict]] = {}
    query = f"{requirement.get('product', '')} {requirement.get('task', '')} {requirement.get('target', '')}"
    for key, cap in _SECTION_CAPABILITY.items():
        if cap not in knowledge_map:
            try:
                knowledge_map[cap] = _search_capability(cap, query)
            except Exception:
                knowledge_map[cap] = []

    knowledge_text = _render_knowledge(knowledge_map)
    requirement_text = _render_requirement(requirement)
    algorithm_text = (
        f"任务: {algorithm.get('task', '')}\n"
        f"推荐算法: {', '.join(algorithm.get('algorithms', []))}\n"
        f"理由: {algorithm.get('reason', '')}"
    )

    prompt = _GENERATE_PROMPT.format(
        requirement=requirement_text,
        algorithm=algorithm_text,
        knowledge=knowledge_text,
    )
    try:
        response = llm.invoke(prompt)
        content = response.content.strip()
    except Exception as e:
        content = f"方案生成失败: {e}"

    sections = []
    for key, title in SOLUTION_SECTIONS:
        sections.append({"key": key, "title": title, "content": content})

    return {
        "requirement": requirement,
        "algorithm": algorithm,
        "sections": sections,
        "knowledge_map": {str(k): v for k, v in knowledge_map.items()},
    }
