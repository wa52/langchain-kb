"""Evidence labels that keep RAG answers within their source boundaries."""

from __future__ import annotations

from pathlib import PurePath


_EXAMPLE_CODE_SUFFIXES = frozenset({".hdev", ".hdvp", ".hdevx"})


def source_evidence_note(source: str) -> str:
    """Return the limitation that applies to a retrieved source.

    HDevelop examples establish that a call occurs in that example. They do
    not, by themselves, document the operator contract. Making that boundary
    explicit prevents the answer model from inventing parameter semantics.
    """
    suffix = PurePath(str(source)).suffix.lower()
    if suffix in _EXAMPLE_CODE_SUFFIXES:
        return "证据类型: HDevelop 示例代码；只能证明示例中出现的调用，不能单独证明算子参数语义、输出类型或适用范围。"
    return "证据类型: 知识库文档片段；仅可据其中明确记载的内容作答。"


def evidence_header(source: str) -> str:
    return f"[来源: {source}]\n[{source_evidence_note(source)}]"
