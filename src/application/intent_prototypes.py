"""Lazy embedding-based intent prototypes for Smart Routing."""

from __future__ import annotations

from collections.abc import Callable
from math import sqrt


_PROTOTYPES = {
    "direct": ("解释一个概念", "翻译这句话", "写一封邮件", "你好"),
    "fast_rag": ("查我的资料", "之前项目怎么实现", "文档里的参数是多少", "之前记录的方案"),
    "agent": ("帮我查 GitHub 最近提交", "帮我创建 issue", "保存到知识库", "修改文件并执行"),
}


class IntentPrototypeClassifier:
    def __init__(self, embed: Callable[[list[str]], list[list[float]]]) -> None:
        self._embed = embed
        self._vectors: dict[str, list[list[float]]] | None = None

    def classify(self, query: str) -> dict[str, float]:
        if self._vectors is None:
            flat = [item for values in _PROTOTYPES.values() for item in values]
            vectors = self._embed(flat)
            cursor = 0
            self._vectors = {}
            for name, values in _PROTOTYPES.items():
                self._vectors[name] = vectors[cursor:cursor + len(values)]
                cursor += len(values)
        query_vector = self._embed([query])[0]
        return {name: round(max((self._cosine(query_vector, vector) for vector in vectors), default=0.0), 3) for name, vectors in self._vectors.items()}

    @staticmethod
    def _cosine(left, right) -> float:
        denominator = sqrt(sum(x * x for x in left)) * sqrt(sum(x * x for x in right))
        return sum(x * y for x, y in zip(left, right)) / denominator if denominator else 0.0
