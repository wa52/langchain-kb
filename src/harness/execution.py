"""Policy-gated, observable execution for registered tools."""

from concurrent.futures import ThreadPoolExecutor, TimeoutError
from dataclasses import dataclass, field
import time
from typing import Any, Callable

from src.harness.tools import ToolSpec


@dataclass(frozen=True)
class ToolResult:
    success: bool
    tool_name: str
    data: Any = None
    error: str | None = None
    error_type: str | None = None
    elapsed_ms: float = 0.0
    retry_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


class ExecutionPolicy:
    def __init__(self, *, approval_required: Callable[[ToolSpec], bool] | None = None, max_retries: int = 1) -> None:
        self._approval_required = approval_required or (lambda spec: spec.risk_level in {"high", "critical"})
        self.max_retries = max(0, max_retries)

    def requires_approval(self, spec: ToolSpec) -> bool:
        return bool(self._approval_required(spec))

    def retry_limit(self, spec: ToolSpec) -> int:
        return self.max_retries if spec.retryable and spec.read_only else 0


class ToolExecutor:
    def __init__(self, policy: ExecutionPolicy | None = None, *, trace: Any = None) -> None:
        self.policy = policy or ExecutionPolicy()
        self.trace = trace

    def execute(self, spec: ToolSpec, kwargs: dict[str, Any], *, approved: bool = False) -> ToolResult:
        started = time.perf_counter()
        if self.trace is not None:
            self.trace.emit("tool.call.started", tool_name=spec.name, arguments=kwargs)
        if self.policy.requires_approval(spec) and not approved:
            result = ToolResult(False, spec.name, error="tool approval required", error_type="APPROVAL_REQUIRED")
            if self.trace is not None: self.trace.record(result, arguments=kwargs)
            return result
        attempts = self.policy.retry_limit(spec)
        for retry_count in range(attempts + 1):
            try:
                with ThreadPoolExecutor(max_workers=1) as pool:
                    future = pool.submit(self._invoke, spec, kwargs)
                    data = future.result(timeout=spec.timeout_seconds)
                result = ToolResult(True, spec.name, data=data, elapsed_ms=self._elapsed(started), retry_count=retry_count)
                if self.trace is not None: self.trace.record(result, arguments=kwargs)
                return result
            except TimeoutError:
                error, error_type = "tool execution timed out", "TIMEOUT"
            except Exception as exc:
                error, error_type = str(exc), "EXECUTION_ERROR"
            if retry_count >= attempts:
                result = ToolResult(False, spec.name, error=error, error_type=error_type, elapsed_ms=self._elapsed(started), retry_count=retry_count)
                if self.trace is not None: self.trace.record(result, arguments=kwargs)
                return result
        raise AssertionError("unreachable")

    @staticmethod
    def _invoke(spec: ToolSpec, kwargs: dict[str, Any]) -> Any:
        invoke = getattr(spec.handler, "invoke", None)
        return invoke(kwargs) if invoke is not None else spec.handler(**kwargs)

    @staticmethod
    def _elapsed(started: float) -> float:
        return round((time.perf_counter() - started) * 1000, 2)
