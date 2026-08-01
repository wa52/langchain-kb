"""Map knowledge chunks onto the industrial vision AI capability model.

Two-layer rule mapping:
  1. map_by_source  - filename/dir heuristics (fast, coarse)
  2. map_by_content - content keyword heuristics (refines domains/items/scene)

Each chunk ends up with multi-label metadata:
  source, technology, scene, capability_domain, capability_items,
  confidence, mapping_method
"""

from src.capability.model import (
    CAPABILITY_DOMAINS,
    DOMAIN_BY_ID,
    technology_from_source,
    scene_from_source,
    scene_from_content,
)

_DEFAULT_DOMAIN = 2  # 知识研究 (unknown content)

# Source-name rules: (substring, domain id, confidence)
_SOURCE_DOMAIN_RULES = [
    ("hdevelop_users_guide", 5, 0.85),     # HDevelop 编程手册 → 工程开发
    ("programmers_guide", 5, 0.85),
    ("installation_guide", 5, 0.8),
    ("extension_package", 5, 0.8),
    ("solution_guide_ii_a", 3, 0.9),       # 图像采集 → 方案设计
    ("image_acquisition", 3, 0.9),
    ("parallel_programming", 5, 0.8),
    ("solution_guide_iii_a", 4, 0.9),      # 1D 测量 → 算法实现
    ("1d_measuring", 4, 0.9),
    ("solution_guide_iii_b", 4, 0.9),      # 2D 测量
    ("2d_measuring", 4, 0.9),
    ("solution_guide_iii_c", 4, 0.9),      # 3D 视觉
    ("3d_vision", 4, 0.9),
    ("solution_guide_ii_b", 4, 0.9),       # 匹配
    ("matching", 4, 0.9),
    ("solution_guide_ii_c", 4, 0.9),       # 2D 数据码 → OCR
    ("data_codes", 4, 0.9),
    ("solution_guide_ii_d", 4, 0.9),       # 分类 → 深度学习
    ("classification", 4, 0.9),
    ("solution_guide_i", 1, 0.85),         # 应用领域总览 → 需求分析
    ("surface_based_matching", 4, 0.9),
    ("quick_guide", 2, 0.8),               # 快速指南 → 知识研究
    ("langchain", 5, 0.8),                 # LangChain 教程 → 工程开发
    ("deepagents", 5, 0.8),                # DeepAgents → 工程开发
    ("langgraph", 5, 0.8),                 # LangGraph → 工程开发
    ("runoob_", 5, 0.7),                   # runoob 教程 → 工程开发
    ("opencv", 4, 0.85),                   # OpenCV 教程 → 算法实现
]

# Source-name rules: (.hdev files → 算法实现)
def _hdev_domain(source: str) -> int | None:
    if source.lower().endswith(".hdev"):
        return 4
    return None


def map_by_source(source: str) -> dict:
    """Rule-based mapping from a source filename to capability domains."""
    low = source.lower()
    domains: set[int] = set()
    confidence = 0.0
    method = "source_rule"

    hd = _hdev_domain(source)
    if hd is not None:
        domains.add(hd)
        confidence = 0.9

    for sub, dom, conf in _SOURCE_DOMAIN_RULES:
        if sub in low:
            domains.add(dom)
            confidence = max(confidence, conf)

    return {
        "domains": sorted(domains),
        "technology": technology_from_source(source),
        "scene": scene_from_source(source),
        "confidence": confidence,
        "method": method,
    }


def map_by_content(text: str) -> dict:
    """Rule-based mapping from chunk content to capability domains."""
    domains: set[int] = set()
    items: set[str] = set()
    for dom in CAPABILITY_DOMAINS:
        dom_id = dom["id"]
        for kw in dom["keywords"]:
            if kw.lower() in text.lower():
                domains.add(dom_id)
                break

    # Specific item-level keywords
    item_map = {
        "4.1": ["预处理", "滤波", "filter", "增强", "灰度", "直方图"],
        "4.2": ["分割", "threshold", "阈值", "blob", "连通域", "形态学"],
        "4.3": ["定位", "匹配", "matching", "模板", "对位", "位置"],
        "4.4": ["缺陷", "defect", "瑕疵", "划痕", "检测"],
        "4.5": ["测量", "measure", "尺寸", "1d_measuring", "2d_measuring"],
        "4.6": ["OCR", "字符", "条码", "二维码", "data_code", "识别"],
        "4.7": ["深度学习", "CNN", "神经网络", "分类", "classification"],
        "4.8": ["3D", "点云", "stereo", "surface_based", "深度"],
        "3.1": ["相机", "camera", "镜头", "光源", "illumination", "标定", "calibration"],
        "3.2": ["FOV", "视野", "分辨率", "景深", "光学"],
        "3.3": ["算法方案", "方案设计", "选型"],
        "5.3": ["PLC", "机器人", "通讯", "串口", "以太网", "集成", "握手"],
    }
    low = text.lower()
    for item, kws in item_map.items():
        if any(k.lower() in low for k in kws):
            items.add(item)
            domains.add(int(item.split(".")[0]))

    return {
        "domains": sorted(domains),
        "items": sorted(items),
        "scene": scene_from_content(text),
        "confidence": 0.8 if (domains or items) else 0.0,
        "method": "content_rule",
    }


def classify_chunk(source: str, text: str) -> dict:
    """Produce multi-label capability metadata for a chunk."""
    src_res = map_by_source(source)
    content_res = map_by_content(text)

    domains = sorted(set(src_res["domains"]) | set(content_res["domains"]))
    items = set(content_res["items"])

    # Source-implied item keywords refine
    low_src = source.lower()
    items_for_source = {
        "1d_measuring": "4.5", "2d_measuring": "4.5", "3d_vision": "4.8",
        "matching": "4.3", "data_codes": "4.6", "classification": "4.7",
        "image_acquisition": "3.1",
    }
    for key, item in items_for_source.items():
        if key in low_src:
            items.add(item)

    if not domains:
        domains = [_DEFAULT_DOMAIN]

    # confidence: source > content, else base
    if src_res["confidence"] >= 0.85:
        confidence = src_res["confidence"]
        method = src_res["method"]
    elif content_res["domains"] or content_res["items"]:
        confidence = content_res["confidence"]
        method = content_res["method"]
    else:
        confidence = 0.5
        method = "default"

    domain_str = ",".join(str(d) for d in domains)
    items_str = ",".join(sorted(items)) if items else ""

    # Primary domain: the highest-confidence single domain, used for exact
    # ($eq) filtering in Chroma where multi-label substrings can't be matched.
    primary = None
    if src_res["domains"] and src_res["confidence"] >= 0.85:
        primary = src_res["domains"][0]
    elif domains:
        primary = domains[0]

    scene = src_res["scene"] or content_res["scene"]
    technology = src_res["technology"]

    return {
        "source": source,
        "technology": technology,
        "scene": scene,
        "capability_domain": domain_str,
        "capability_domain_primary": str(primary) if primary else "",
        "capability_items": items_str,
        "confidence": round(confidence, 2),
        "mapping_method": method,
    }
