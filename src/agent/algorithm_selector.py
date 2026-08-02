"""Stage 4: algorithm selection for a detection task.

Rule-based mapping from detection task to recommended algorithm families,
optionally enriched with capability-4 (算法实现) knowledge retrieval.
"""

TASK_ALGORITHM_RULES = {
    "测量": {
        "algorithms": ["边缘检测", "卡尺工具", "亚像素拟合"],
        "reason": "高精度尺寸测量需边缘定位 + 卡尺 + 亚像素插值",
    },
    "定位": {
        "algorithms": ["模板匹配", "特征匹配", "形状匹配"],
        "reason": "稳定对位需基于灰度/形状/特征模板匹配",
    },
    "缺陷": {
        "algorithms": ["Blob分析", "图像分割", "异常检测"],
        "reason": "区域特征分析（连通域、形态学），可选深度学习异常检测",
    },
    "OCR": {
        "algorithms": ["OCR模型", "条码/二维码识别"],
        "reason": "字符识别需 OCR 引擎或数据码解码",
    },
}

_TASK_KEYWORDS = {
    "测量": ["测量", "尺寸", "长度", "宽度", "角度", "measure"],
    "定位": ["定位", "对位", "位置", "position", "匹配"],
    "缺陷": ["缺陷", "检测", "划痕", "瑕疵", "inspection", "defect", "scratch"],
    "OCR": ["OCR", "字符", "条码", "二维码", "识别", "data code"],
}


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


def _resolve_task(task: str) -> str:
    """Map a free-text task onto a known rule category."""
    low = (task or "").lower()
    for cat, kws in _TASK_KEYWORDS.items():
        if any(k.lower() in low for k in kws):
            return cat
    if not task:
        return "缺陷"  # default most common
    return task


def select_algorithm(task: str, scene: str = "", llm=None) -> dict:
    """Recommend algorithms for a detection task.

    Returns: {task, algorithms[], reason, knowledge_refs[]}
    knowledge_refs filled from capability-4 retrieval when llm/scene allow.
    """
    category = _resolve_task(task)
    rule = TASK_ALGORITHM_RULES.get(category, {
        "algorithms": ["图像预处理", "分割", "目标分析"],
        "reason": "通用视觉处理流程",
    })

    result = {
        "task": task,
        "category": category,
        "algorithms": list(rule["algorithms"]),
        "reason": rule["reason"],
        "knowledge_refs": [],
    }

    # Enrich with capability-4 knowledge when not in test mode (llm provided)
    if llm is not None:
        try:
            refs = _search_capability(4, f"{task} {category} 算法", k=3)
            result["knowledge_refs"] = refs
        except Exception:
            pass

    return result


_LLM_REFINE_PROMPT = """你是一名工业视觉算法专家。基于给定的检测任务、初始算法推荐和知识库检索结果，
给出更具体的算子/算法细化建议。

只输出一个 JSON 对象，不要其他内容，不要使用代码块标记:
{{"operators": ["算子1", "算子2"], "refinements": "一段简短中文细化说明"}}

- operators: 3-5 个具体算子/API（如 HALCON 的 threshold、connection，或 OpenCV 的 cv2.threshold）
- refinements: 最多 100 字的中文说明（补充/调整理由）

任务: {task}
初始推荐算法: {algorithms}
理由: {reason}
知识库参考:
{knowledge}
"""


def select_algorithm_llm(task: str, scene: str = "", llm=None) -> dict:
    """Recommend algorithms with LLM refinement.

    Rule table provides the baseline (+ capability-4 retrieval), then one
    LLM call refines with concrete operators and adjustments.
    Returns: {task, algorithms, reason, knowledge_refs, llm_refinements,
              operators[]}
    """
    base = select_algorithm(task, scene, llm=llm)

    result = {
        "task": base["task"],
        "category": base["category"],
        "algorithms": base["algorithms"],
        "reason": base["reason"],
        "knowledge_refs": base.get("knowledge_refs", []),
        "llm_refinements": "",
        "operators": [],
    }

    if llm is None:
        return result

    knowledge_text = "\n".join(
        f"- [{r['source']}] {r['content'][:120]}" for r in base.get("knowledge_refs", [])[:5]
    )
    prompt = _LLM_REFINE_PROMPT.format(
        task=task,
        algorithms=", ".join(base["algorithms"]),
        reason=base["reason"],
        knowledge=knowledge_text or "（无）",
    )
    try:
        import json
        import re
        response = llm.invoke(prompt)
        content = response.content.strip()
        if content.startswith("```"):
            content = content.strip("`")
            if content.startswith("json"):
                content = content[4:]
        # Robust JSON extraction: find the first {...} object.
        m = re.search(r"\{.*\}", content, re.DOTALL)
        data = json.loads(m.group(0)) if m else json.loads(content)
        result["operators"] = list(data.get("operators", []) or [])
        result["llm_refinements"] = str(data.get("refinements", "") or "")
    except Exception as e:
        result["llm_refinements"] = ""
        print(f"  [算法细化] LLM 调用失败: {e}，使用规则表推荐")

    return result
