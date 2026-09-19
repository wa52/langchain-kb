"""Deterministic, metadata-driven candidate selection for Agent tools."""

from collections.abc import Iterable
from dataclasses import dataclass
import re
from typing import Protocol

from src.harness.tools import ToolSpec


_QUERY_TAG_ALIASES = {
    "知识": {"knowledge", "search"},
    "文档": {"knowledge", "search", "read"},
    "资料": {"knowledge", "search", "read"},
    "查询": {"search", "read"},
    "搜索": {"search", "read"},
    "关系": {"graph", "knowledge", "search"},
    "图谱": {"graph", "knowledge", "search"},
    "保存": {"write"},
    "写入": {"write"},
    "创建": {"write", "create"},
    "github": {"github"},
    "飞书": {"feishu"},
}


@dataclass(frozen=True)
class ToolCandidate:
    """A selected ToolSpec plus the deterministic score used to select it."""

    spec: ToolSpec
    score: float


@dataclass(frozen=True)
class ToolSelectionContext:
    """Structured route facts supplied by the Decision Layer."""

    intent: str
    domain: str = "general"
    side_effect: bool = False


class ToolSelector(Protocol):
    """Stable selection port implemented by rule-based and remote adapters."""

    def select(self, query: str, tools: Iterable[ToolSpec], *, context: ToolSelectionContext | None = None) -> tuple[ToolCandidate, ...]: ...

    def select_names(self, query: str, tools: Iterable[ToolSpec], *, context: ToolSelectionContext | None = None) -> tuple[str, ...]: ...


class RuleBasedToolSelector:
    """Choose a compact tool set from the ToolRegistry catalog.

    This first implementation is deliberately deterministic: it uses tool
    tags, server identifiers, names and descriptions. It is the default
    offline implementation and the fallback for a future Jev adapter.
    """

    def __init__(self, *, max_candidates: int = 8, min_candidates: int = 3) -> None:
        if not 1 <= min_candidates <= max_candidates:
            raise ValueError("min_candidates must be between 1 and max_candidates")
        self._max_candidates = max_candidates
        self._min_candidates = min_candidates

    @staticmethod
    def _terms(query: str) -> set[str]:
        terms = set(re.findall(r"[a-z0-9_]+", query.lower()))
        for phrase in re.findall(r"[\u4e00-\u9fff]{2,}", query):
            terms.add(phrase)
            terms.update(phrase[index:index + 2] for index in range(len(phrase) - 1))
        return terms

    @staticmethod
    def _query_tags(query: str) -> set[str]:
        normalized = query.lower()
        tags = {alias for keyword, aliases in _QUERY_TAG_ALIASES.items() if keyword in normalized for alias in aliases}
        return tags | (set(re.findall(r"[a-z0-9_]+", normalized)) & {"github", "feishu"})

    def select(self, query: str, tools: Iterable[ToolSpec], *, context: ToolSelectionContext | None = None) -> tuple[ToolCandidate, ...]:
        """Return up to ``max_candidates`` enabled tools ordered by relevance."""
        terms = self._terms(query)
        requested_tags = self._query_tags(query)
        write_requested = bool(requested_tags & {"write", "create"})
        if context is not None:
            if context.domain != "general":
                requested_tags.add(context.domain)
            write_requested = context.side_effect
        candidates: list[ToolCandidate] = []
        fallback: list[ToolSpec] = []

        for spec in tools:
            if not spec.enabled:
                continue
            fallback.append(spec)
            # Metadata can share domain tags (for example knowledge search and
            # knowledge write).  A read-style question must not surface a
            # mutating tool merely because it belongs to the same domain.
            if not write_requested and not spec.read_only:
                continue
            tags = set(spec.tags)
            searchable = f"{spec.name} {spec.server_id or ''} {spec.description}".lower()
            score = 12 * len(tags & requested_tags)
            score += 6 * sum(term in searchable for term in terms)
            score += 3 * sum(term in tags for term in terms)
            if score:
                candidates.append(ToolCandidate(spec, score))

        candidates.sort(key=lambda item: (-item.score, item.spec.name))
        selected = candidates[:self._max_candidates]
        selected_names = {item.spec.name for item in selected}
        # A small read-only fallback lets the model still answer when query
        # wording has no keyword overlap, without exposing every write tool.
        for spec in sorted(fallback, key=lambda item: item.name):
            if len(selected) >= self._min_candidates or len(selected) >= self._max_candidates:
                break
            if spec.name not in selected_names and spec.read_only:
                selected.append(ToolCandidate(spec, 0))
                selected_names.add(spec.name)
        return tuple(selected)

    def select_names(self, query: str, tools: Iterable[ToolSpec], *, context: ToolSelectionContext | None = None) -> tuple[str, ...]:
        return tuple(candidate.spec.name for candidate in self.select(query, tools, context=context))
