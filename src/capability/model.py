"""Industrial vision AI engineer capability model.

Defines the capability domains that organize knowledge, plus technology
and scene taxonomies and the keyword tables used to map content onto
capabilities. Sources (HALCON, OpenCV, ...) are not the primary axis:
knowledge is mapped to what the AI engineer can DO with it.
"""

# ---- Capability domains (7) ------------------------------------------------

CAPABILITY_DOMAINS = [
    {
        "id": 1,
        "name": "需求分析",
        "items": ["1.1 检测目标识别", "1.2 技术指标提取", "1.3 可行性评估"],
        "keywords": ["需求分析", "检测目标", "精度要求", "节拍", "可行性", "技术指标",
                     "defect", "requirement", "spec", "takt", "accuracy"],
    },
    {
        "id": 2,
        "name": "知识研究",
        "items": ["2.1 知识检索", "2.2 知识综合", "2.3 技术选型调研"],
        "keywords": ["综述", "调研", "技术选型", "对比", "survey", "research",
                     "literature", "overview", "评估对比"],
    },
    {
        "id": 3,
        "name": "方案设计",
        "items": ["3.1 成像系统设计", "3.2 光学计算", "3.3 算法方案设计", "3.4 系统架构"],
        "keywords": ["相机", "镜头", "光源", "打光", "视野", "FOV", "分辨率", "景深",
                     "标定", "calibration", "illumination", "camera", "lens",
                     "optics", "方案设计", "光路", "成像"],
    },
    {
        "id": 4,
        "name": "算法实现",
        "items": ["4.1 图像预处理", "4.2 图像分割", "4.3 图像定位", "4.4 缺陷检测",
                  "4.5 尺寸测量", "4.6 字符识别", "4.7 深度学习视觉", "4.8 3D视觉"],
        "keywords": ["threshold", "分割", "blob", "边缘", "edge", "缺陷", "defect",
                     "测量", "measure", "匹配", "matching", "定位", "OCR", "条码",
                     "二维码", "识别", "深度学习", "CNN", "神经网络", "深度学习视觉",
                     "3D", "点云", "segmentation", "filter", "形态学", "模板匹配",
                     "read_image", "图像处理", "连通域", "轮廓"],
    },
    {
        "id": 5,
        "name": "工程开发",
        "items": ["5.1 视觉程序设计", "5.2 SDK集成", "5.3 系统集成", "5.4 部署"],
        "keywords": ["PLC", "机器人", "通讯", "接口", "SDK", "API", "编程", "开发",
                     "程序", "HDevelop", "部署", "集成", "robot", "串口", "以太网",
                     "采集卡", "MFC", "C#", "C++", "Python", "上位机"],
    },
    {
        "id": 6,
        "name": "项目验证",
        "items": ["6.1 现场调试", "6.2 鲁棒性", "6.3 性能优化", "6.4 验收"],
        "keywords": ["调试", "鲁棒", "优化", "性能", "验收", "现场", "节拍优化",
                     "稳定", "鲁棒性", "troubleshoot", "debug", "optimize", "验收标准"],
    },
    {
        "id": 7,
        "name": "能力评估",
        "items": ["7.1 方案评估", "7.2 算法对比", "7.3 持续优化"],
        "keywords": ["评估", "对比测试", "benchmark", "评测", "方案对比", "精度评估"],
    },
]

DOMAIN_BY_ID = {d["id"]: d for d in CAPABILITY_DOMAINS}

# ---- Technology (source tech) ---------------------------------------------

TECHNOLOGIES = [
    "halcon", "opencv", "langchain", "deepagents", "langgraph",
    "pytorch", "tensorflow", "cuda", "python", "csharp", "cpp",
]


def technology_from_source(source: str) -> str:
    """Guess the technology from a source filename."""
    low = source.lower()
    if ".hdev" in low or "halcon" in low or "hdevelop" in low:
        return "halcon"
    if "opencv" in low:
        return "opencv"
    if "langgraph" in low:
        return "langgraph"
    if "deepagents" in low:
        return "deepagents"
    if "langchain" in low:
        return "langchain"
    if "pytorch" in low or "torch" in low:
        return "pytorch"
    if "tensorflow" in low:
        return "tensorflow"
    if "cuda" in low:
        return "cuda"
    return ""


# ---- Scene taxonomy ---------------------------------------------------------

SCENES = {
    "defect_inspection": ["缺陷", "defect", "inspection", "瑕疵", "检测缺陷", "划痕", "污渍"],
    "measurement": ["测量", "measure", "尺寸", "1d", "2d_measuring", "3d_measuring", "长度", "角度"],
    "ocr": ["OCR", "字符", "条码", "二维码", "data_code", "barcode", "text", "识别字符"],
    "positioning": ["定位", "position", "匹配", "matching", "对位", "mark", "模板匹配"],
    "classification": ["分类", "classification", "classify", "分拣"],
    "3d_vision": ["3D", "3d", "点云", "point_cloud", "深度", "stereo", "surface_based"],
    "counting": ["计数", "count", "数量", "数数"],
    "image_acquisition": ["image_acquisition", "图像采集", "采像", "acquire", "采集"],
    "general": ["图像处理", "image_processing", "基础", "入门", "tutorial", "overview"],
}


def scene_from_source(source: str) -> str:
    """Guess the industrial scene from a source filename."""
    low = source.lower()
    for scene, keys in SCENES.items():
        if scene == "general":
            continue
        for k in keys:
            if k.lower() in low:
                return scene
    return ""


def scene_from_content(text: str) -> str:
    """Guess the scene from chunk content keywords."""
    for scene, keys in SCENES.items():
        for k in keys:
            if k.lower() in text.lower():
                return scene
    return ""
