"""Guided industrial-vision project workflow (stage 3).

Turns the knowledge base into an AI engineer that walks a project through
the six capability stages — 需求分析 → 知识研究 → 方案设计 → 算法实现 →
工程开发 → 项目验证 — retrieving capability-scoped knowledge at each step.
"""

from langchain.tools import tool

# Project stages: each maps to a capability domain and the key questions
# an AI engineer must answer at that stage of an industrial-vision project.
PROJECT_STAGES = [
    {
        "id": 1,
        "name": "需求分析",
        "capability": 1,
        "description": "明确检测目标、技术指标、环境约束与可行性",
        "questions": [
            "检测对象是什么？缺陷/尺寸/定位/识别/测量哪类？",
            "要求精度、速度、节拍是多少？",
            "现场环境（光照、温度、震动）有何约束？",
            "可接受的成本与交付周期？",
        ],
    },
    {
        "id": 2,
        "name": "知识研究",
        "capability": 2,
        "description": "检索、学习并综合与任务相关的算法规程、案例和最佳实践",
        "questions": [
            "同类项目（缺陷/测量/OCR）常用哪些方案？",
            "有哪些成熟的算子或模型可直接参考？",
            "前人遇到过哪些坑、如何解决？",
        ],
    },
    {
        "id": 3,
        "name": "方案设计",
        "capability": 3,
        "description": "设计成像系统与算法整体方案",
        "questions": [
            "选什么相机、镜头、光源？FOV/分辨率/景深是否满足？",
            "打光方案如何设计（明场/暗场/背光）？",
            "算法流程如何组织？是否需要标定？",
            "系统架构（相机数、触发方式、通讯）如何？",
        ],
    },
    {
        "id": 4,
        "name": "算法实现",
        "capability": 4,
        "description": "选择并实现达成目标的具体算法",
        "questions": [
            "预处理（滤波/增强/矫正）用什么？",
            "分割/定位/检测/测量/OCR 选哪类算法？",
            "是否需深度学习模型？训练数据与标注如何准备？",
            "算法参数如何设定与调优？",
        ],
    },
    {
        "id": 5,
        "name": "工程开发",
        "capability": 5,
        "description": "将算法落地为可交付的系统（代码、SDK、集成）",
        "questions": [
            "用什么语言/SDK 实现（HALCON/OpenCV/自研）？",
            "如何与 PLC/机器人/上位机通讯？",
            "界面与部署方案？异常与重试如何处理？",
        ],
    },
    {
        "id": 6,
        "name": "项目验证",
        "capability": 6,
        "description": "现场调试、鲁棒性验证、性能优化与验收",
        "questions": [
            "现场打光与图像质量如何调试？",
            "算法鲁棒性（变光照/来料波动）如何验证？",
            "节拍能否满足？性能如何优化？",
            "验收标准是什么？如何沉淀经验？",
        ],
    },
]

_STAGE_BY_NAME = {s["name"]: s for s in PROJECT_STAGES}


def _resolve_stage(stage: str) -> dict | None:
    if not stage:
        return None
    s = stage.strip()
    for item in PROJECT_STAGES:
        if s == item["name"] or s == str(item["id"]) or s in item["name"]:
            return item
    return None


def _search_for_stage(query: str, capability: int, k: int = 5) -> list[dict]:
    """Retrieve capability-scoped knowledge for a stage (real vector search)."""
    from src.vector_store.service import VectorStoreService
    retriever = VectorStoreService().get_retriever(k=k, capability=str(capability))
    docs = retriever.invoke(query)
    return [
        {"source": d.metadata.get("source", "unknown"),
         "content": d.page_content[:500]}
        for d in docs
    ]


def build_workflow_prompt() -> str:
    """System-prompt fragment describing the guided workflow."""
    lines = [
        "你是一名工业视觉 AI 工程师，能够引导用户完成一个完整的工业视觉项目。",
        "项目的推进按以下 6 个能力阶段进行：",
    ]
    for s in PROJECT_STAGES:
        lines.append(f"  {s['id']}. {s['name']} — {s['description']}")
    lines.append("使用 project_workflow 工具按阶段推进，每阶段先给出关键问题，再基于检索到的知识给出建议。")
    return "\n".join(lines)


@tool
def project_workflow(project_desc: str, stage: str) -> str:
    """按工业视觉项目阶段引导：给定项目描述和当前阶段，返回该阶段的关键问题与相关知识。

    stage 可为阶段名（需求分析/知识研究/方案设计/算法实现/工程开发/项目验证）或编号（1-6）。
    当用户描述一个工业视觉项目时，使用本工具按阶段推进项目。"""
    stage_info = _resolve_stage(stage)

    if stage_info is None:
        stages = "\n".join(
            f"{s['id']}. {s['name']} — {s['description']}"
            for s in PROJECT_STAGES
        )
        return (
            f"项目: {project_desc}\n\n"
            "请选择项目阶段（可用阶段名或编号）：\n" + stages
        )

    # Retrieve capability-scoped knowledge for this stage
    try:
        results = _search_for_stage(project_desc, stage_info["capability"])
    except Exception as e:
        results = []
        print(f"  [工作流] 检索失败: {e}")

    out = [
        f"## 阶段 {stage_info['id']}: {stage_info['name']}",
        f"任务: {stage_info['description']}",
        "",
        "### 需要明确的问题",
    ]
    for q in stage_info["questions"]:
        out.append(f"- {q}")

    if results:
        out.append("\n### 该阶段相关知识（来自知识库）")
        for r in results[:5]:
            out.append(f"- [{r['source']}] {r['content'][:200]}")
    else:
        out.append("\n（知识库中该能力域暂无相关检索结果，可补充资料后重试）")

    out.append("\n请根据以上内容回答关键问题，然后进入下一阶段。")
    return "\n".join(out)
