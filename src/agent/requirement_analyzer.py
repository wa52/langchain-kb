"""Stage 4: natural-language requirement → structured project requirement.

One LLM call parses a one-line project description (e.g. "设计一个PCB缺陷
检测系统") into structured fields, flagging anything not specified as unknown.
"""

import json

_ANALYZE_PROMPT = """你是一名工业视觉方案分析师。请将以下项目需求解析为结构化字段。
只输出 JSON，不要其他内容。

字段:
- product: 检测对象/产品（如 PCB、手机外壳）
- task: 检测任务类型（如 缺陷检测、尺寸测量、OCR、定位）
- target: 具体检测目标（如 划痕、异物、缺件）
- precision: 精度要求（未说明则填空）
- speed: 速度/节拍要求（未说明则填空）
- environment: 环境约束（光照、温度等，未说明则填空）
- unknown: 未明确的需求点列表（数组）

项目需求: {text}
"""


def analyze_requirement(text: str, llm) -> dict:
    """Parse a natural-language project description into a structured dict."""
    try:
        prompt = _ANALYZE_PROMPT.format(text=text)
        response = llm.invoke(prompt)
        content = response.content.strip()
        if content.startswith("```"):
            content = content.strip("`")
            if content.startswith("json"):
                content = content[4:]
        data = json.loads(content)
        return {
            "product": str(data.get("product", "")),
            "task": str(data.get("task", "")),
            "target": str(data.get("target", "")),
            "precision": str(data.get("precision", "")),
            "speed": str(data.get("speed", "")),
            "environment": str(data.get("environment", "")),
            "unknown": list(data.get("unknown", []) or []),
        }
    except Exception:
        return {
            "product": text,
            "task": "",
            "target": "",
            "precision": "",
            "speed": "",
            "environment": "",
            "unknown": [],
        }
