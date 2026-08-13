"""监控层：运行时组件状态注册表。

分层架构中的监控层，为健康检查、Web 状态接口与交互式控制台提供
关键环节（embedding / llm / vector_store / bm25 / graph / agent / index）
的单一数据源。各层通过 `set_loading/set_ready/set_error/set_disabled`
上报状态，不依赖具体实现；读取方只消费 `snapshot_status()`。

状态机：pending（未启动）→ loading（初始化中）→ ready（就绪）
        或 → error（失败）；disabled（功能关闭，不参与就绪判定）。
"""

from __future__ import annotations

import threading
import time
from typing import Any, Optional

# 组件状态
PENDING = "pending"
LOADING = "loading"
READY = "ready"
ERROR = "error"
DISABLED = "disabled"

# 受监控的关键组件（顺序即展示顺序）
DEFAULT_COMPONENTS = (
    "embedding",
    "llm",
    "vector_store",
    "bm25",
    "graph",
    "agent",
    "index",
)

# 判定整体状态所需的核心组件（任一 error → 整体 error）
CORE_COMPONENTS = ("embedding", "llm", "vector_store")
# 可选组件（error 只导致整体降级）
OPTIONAL_COMPONENTS = ("bm25", "graph")


def _blank(name: str) -> dict[str, Any]:
    return {
        "name": name,
        "state": PENDING,
        "detail": "",
        "started_at": None,
        "duration_ms": None,
        "error": None,
    }


class SystemStatus:
    """进程级组件状态注册表（线程安全）。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._components: dict[str, dict[str, Any]] = {}
        for name in DEFAULT_COMPONENTS:
            self._components[name] = _blank(name)

    def set_loading(self, name: str, detail: str = "") -> None:
        with self._lock:
            c = self._components.setdefault(name, _blank(name))
            c.update(
                state=LOADING,
                detail=detail,
                started_at=time.time(),
                duration_ms=None,
                error=None,
            )

    def set_ready(self, name: str, detail: str = "", duration_ms: Optional[float] = None) -> None:
        with self._lock:
            c = self._components.setdefault(name, _blank(name))
            elapsed = duration_ms
            if elapsed is None and c.get("started_at"):
                elapsed = (time.time() - c["started_at"]) * 1000.0
            c.update(
                state=READY,
                detail=detail,
                started_at=None,
                duration_ms=round(elapsed, 1) if elapsed is not None else None,
                error=None,
            )

    def set_error(self, name: str, error: Any, detail: str = "") -> None:
        with self._lock:
            c = self._components.setdefault(name, _blank(name))
            c.update(state=ERROR, detail=detail, error=str(error)[:500])

    def set_disabled(self, name: str, detail: str = "") -> None:
        with self._lock:
            c = self._components.setdefault(name, _blank(name))
            c.update(
                state=DISABLED, detail=detail, started_at=None, duration_ms=None, error=None
            )

    def reset_all(self) -> None:
        """关闭/回滚后复位为 pending（保留组件集合）。"""
        with self._lock:
            for name in list(self._components):
                self._components[name] = _blank(name)

    def snapshot(self) -> dict[str, dict[str, Any]]:
        with self._lock:
            return {name: dict(c) for name, c in self._components.items()}

    def get(self, name: str) -> dict[str, Any]:
        with self._lock:
            return dict(self._components.setdefault(name, _blank(name)))


class ComponentMonitor:
    """上下文管理器：进入时标记 loading，正常结束由调用方 ok() 标记 ready，
    异常退出自动标记 error 并重新抛出。"""

    def __init__(self, registry: SystemStatus, name: str, detail: str = "") -> None:
        self._registry = registry
        self._name = name
        self._detail = detail

    def __enter__(self) -> "ComponentMonitor":
        self._registry.set_loading(self._name, self._detail)
        return self

    def ok(self, detail: Optional[str] = None) -> None:
        self._registry.set_ready(self._name, detail or self._detail)

    def __exit__(self, exc_type, exc, tb) -> bool:
        if exc_type is not None:
            self._registry.set_error(self._name, exc, self._detail)
        return False


_registry = SystemStatus()

# 进程启动时刻（uptime 基准，与 health 模块各自近似）
_process_started_at: float = time.time()


def get_registry() -> SystemStatus:
    return _registry


def monitor(name: str, detail: str = "") -> ComponentMonitor:
    return ComponentMonitor(_registry, name, detail)


def snapshot_status() -> dict[str, dict[str, Any]]:
    return _registry.snapshot()


def reset_status() -> None:
    _registry.reset_all()


def uptime_seconds() -> float:
    return time.time() - _process_started_at


def overall_state(components: Optional[dict[str, dict[str, Any]]] = None) -> str:
    """由组件状态推导整体状态。

    error：任一核心组件失败；
    ok：核心组件全部就绪且可选组件无失败；
    degraded：核心就绪但可选组件（bm25/graph）失败；
    pending：其余（含正在加载）。
    """
    snap = components if components is not None else _registry.snapshot()
    states = {name: snap.get(name, _blank(name))["state"] for name in snap}
    if any(states.get(n) == ERROR for n in CORE_COMPONENTS):
        return ERROR
    core_ok = all(states.get(n) == READY for n in CORE_COMPONENTS)
    if not core_ok:
        return PENDING
    if any(states.get(n) == ERROR for n in OPTIONAL_COMPONENTS):
        return "degraded"
    return "ok"
