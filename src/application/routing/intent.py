"""Classify intent without selecting a tool or probing retrieval."""

from __future__ import annotations

import re
from typing import Any

from src.domain.routing import Intent, IntentAssessment


_ACTION_VERBS = "创建|新建|建立|删除|修改|发送|保存|存入|记录|发布|写入|执行|运行|提交|推送"
_REQUEST_PREFIXES = "帮我|请|给我|麻烦|劳烦|替我|为我|现在|去"
_MUTATING_ACTION = re.compile(rf"^(?:{_ACTION_VERBS})|^(?:把|将).{{0,30}}(?:{_ACTION_VERBS})|(?:{_REQUEST_PREFIXES}).{{0,16}}(?:{_ACTION_VERBS})", re.I)
_ACTION_CONCEPT = re.compile(rf"(?:{_ACTION_VERBS}).{{0,18}}(?:是什么|为什么|为何|哪些|怎么|如何|通常|一般|区别|用途|意义|作用)", re.I)
_EXTERNAL_ACTION = re.compile(
    rf"(?:{_REQUEST_PREFIXES}).{{0,36}}(?:(?:查|搜索|看看|看一下|查看|检查|查询).{{0,24}}(?:github|仓库|网页|官网|最新|commit|提交|issue)|(?:github|仓库|网页|官网).{{0,24}}(?:查|搜索|看看|看一下|查看|检查|查询))"
    r"|(?:查|搜索|检查).{0,20}(?:github|仓库|网页|官网)|(?:帮我|请).{0,12}(?:联网|调用工具|mcp)|(?:用|调用|使用).{0,8}(?:mcp|工具)|(?:读取|查看).{0,12}(?:仓库|文件)",
    re.I,
)
_FILESYSTEM_TARGET = re.compile(r"(?:文件|目录|文件夹|路径|本地|磁盘|[a-z]:[\\/])", re.I)
_FILESYSTEM_ACTION = re.compile(
    r"(?:读取|查看|列出|搜索|查找|比较|比对|对比|检查|扫描|去重|导入|索引|入库|加入|添加|复制|移动|删除|修改|更新)"
    r"|把.{0,60}(?:比较|比对|对比|去重|导入|索引|入库|加入|添加)",
    re.I,
)
_FILESYSTEM_CONCEPT = re.compile(
    r"(?:怎么|如何|为什么|为何|是什么|区别|原理|含义).{0,24}(?:文件|目录|文件夹|路径|本地|磁盘)"
    r"|(?:读取|查看|列出|搜索|查找|比较|比对|对比|扫描|去重|导入|索引|入库|加入|添加)"
    r".{0,16}(?:怎么|如何|为什么|为何|是什么|区别|原理|含义)",
    re.I,
)
_FILESYSTEM_MUTATION = re.compile(r"(?:导入|索引|入库|加入|添加|复制|移动|删除|修改|更新|写入|保存)", re.I)
_DIRECT_TASKS = ("翻译", "润色", "改写", "写一封", "解释", "计算")
_KNOWLEDGE_HINTS = (
    "知识库", "资料", "文档", "之前", "以前", "先前", "历史", "项目里", "项目的", "当时", "上次", "我们", "我那个", "我这个",
    "项目", "方案", "训练", "检测", "标定", "halcon", "aoi", "ocr", "视觉", "相机", "镜头", "光源", "缺陷", "检索", "查找",
)
_DOMAINS = {"github": ("github", "commit", "issue", "pull request", "仓库"), "web": ("网页", "官网", "联网", "最新"), "mcp": ("mcp", "工具"), "knowledge": ("知识库", "资料", "文档", "项目", "rag")}


class IntentClassifier:
    """A deep module that exposes structured Direct/Knowledge/Action facts."""

    def __init__(self, prototype_classifier: Any | None = None) -> None:
        self._prototype_classifier = prototype_classifier

    def assess(self, query: str) -> IntentAssessment:
        text = " ".join((query or "").strip().lower().split())
        scores = self._prototype_classifier.classify(query) if self._prototype_classifier is not None else {}
        filesystem_action = bool(
            _FILESYSTEM_TARGET.search(text)
            and _FILESYSTEM_ACTION.search(text)
            and not _FILESYSTEM_CONCEPT.search(text)
        )
        if filesystem_action:
            return IntentAssessment(
                Intent.ACTION,
                "filesystem",
                bool(_FILESYSTEM_MUTATION.search(text)),
                1.0,
                ("local_filesystem_action",),
            )
        domain = self._domain(text)
        if not _ACTION_CONCEPT.search(text) and (_MUTATING_ACTION.search(text) or _EXTERNAL_ACTION.search(text)):
            return IntentAssessment(Intent.ACTION, domain, bool(_MUTATING_ACTION.search(text)), 1.0, ("explicit_action_request",))
        if any(task in text for task in _DIRECT_TASKS) and not any(hint in text for hint in _KNOWLEDGE_HINTS):
            return IntentAssessment(Intent.DIRECT, domain, False, 0.95, ("direct_task",))
        if any(hint in text for hint in _KNOWLEDGE_HINTS) or scores.get("fast_rag", 0.0) >= 0.70:
            return IntentAssessment(Intent.KNOWLEDGE, "knowledge", False, max(0.70, float(scores.get("fast_rag", 0.0))), ("knowledge_intent",))
        if scores.get("agent", 0.0) >= 0.82 and scores.get("agent", 0.0) > scores.get("direct", 0.0):
            return IntentAssessment(Intent.ACTION, domain, False, float(scores["agent"]), ("prototype_action",))
        return IntentAssessment(Intent.DIRECT, domain, False, max(0.5, float(scores.get("direct", 0.0))), ("general_direct",))

    @staticmethod
    def _domain(text: str) -> str:
        for domain, terms in _DOMAINS.items():
            if any(term in text for term in terms):
                return domain
        return "general"
