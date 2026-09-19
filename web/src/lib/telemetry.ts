import { useSyncExternalStore } from "react";

export interface RunTelemetry {
  startedAt: number | null;
  elapsedMs: number | null;
  sourceCount: number | null;
  hitChain: string[];
  tools: string[];
  error: string | null;
  traceRunId: string | null;
  actions: ActionTelemetry[];
}

export interface ActionTelemetry {
  name: string;
  at: number;
  elapsedMs: number | null;
  status?: string;
  detail?: string;
  children?: ActionTelemetry[];
}

export interface ApiErrorEntry {
  url: string;
  status: number;
  at: number;
}

export interface DevTelemetry {
  streamEvents: Record<string, number>;
  lastStreamEvent: string | null;
  lastRun: RunTelemetry;
  apiErrors: ApiErrorEntry[];
}

const MAX_API_ERRORS = 20;

let telemetry: DevTelemetry = {
  streamEvents: {},
  lastStreamEvent: null,
  lastRun: {
    startedAt: null,
    elapsedMs: null,
    sourceCount: null,
    hitChain: [],
    tools: [],
    error: null,
    traceRunId: null,
    actions: [],
  },
  apiErrors: [],
};

const listeners = new Set<() => void>();

function emit(): void {
  for (const l of listeners) l();
}

export function resetDevTelemetry(): void {
  telemetry = {
    streamEvents: {},
    lastStreamEvent: null,
    lastRun: {
      startedAt: null,
      elapsedMs: null,
      sourceCount: null,
      hitChain: [],
      tools: [],
      error: null,
      traceRunId: null,
      actions: [],
    },
    apiErrors: [],
  };
  emit();
}

export function recordStreamEvent(type: string): void {
  const now = Date.now();
  const previous = telemetry.lastRun.actions.length
    ? telemetry.lastRun.actions[telemetry.lastRun.actions.length - 1].at
    : telemetry.lastRun.startedAt;
  telemetry = {
    ...telemetry,
    streamEvents: {
      ...telemetry.streamEvents,
      [type]: (telemetry.streamEvents[type] ?? 0) + 1,
    },
    lastStreamEvent: type,
    lastRun: {
      ...telemetry.lastRun,
      actions: [...telemetry.lastRun.actions, {
        name: type,
        at: now,
        elapsedMs: previous == null ? null : now - previous,
      }],
    },
  };
  emit();
}

export function recordRunStart(): void {
  telemetry = {
    ...telemetry,
    lastRun: {
      startedAt: Date.now(),
      elapsedMs: null,
      sourceCount: null,
      hitChain: [],
      tools: [],
      error: null,
      traceRunId: null,
      actions: [],
    },
  };
  emit();
}

export function recordAgentTrace(trace: {
  run_id: string;
  events: Array<{ type: string; payload?: Record<string, unknown>; created_at: string }>;
}): void {
  const startedAt = new Map<string, number>();
  const actions: ActionTelemetry[] = [];
  for (const event of trace.events ?? []) {
    const parsed = Date.parse(event.created_at);
    const at = Number.isFinite(parsed) ? parsed : Date.now();
    const payload = event.payload ?? {};
    if (event.type === "selector.started") {
      startedAt.set("selector", at);
      continue;
    }
    if (event.type === "selector.completed") {
      const selected = Array.isArray(payload.selected_tools)
        ? payload.selected_tools.map(String)
        : [];
      actions.push({
        name: "工具选择",
        at,
        elapsedMs: startedAt.has("selector") ? at - (startedAt.get("selector") ?? at) : null,
        detail: selected.length ? selected.join(", ") : "未选择工具",
      });
      continue;
    }
    if (event.type === "llm.response") {
      const duration = payload.duration_ms;
      const sequence = payload.sequence;
      const toolCalls = Array.isArray(payload.tool_calls) ? payload.tool_calls.map(String) : [];
      actions.push({
        name: `LLM #${typeof sequence === "number" ? sequence : actions.length + 1}`,
        at,
        elapsedMs: typeof duration === "number" ? duration : null,
        status: typeof payload.status === "string" ? payload.status : undefined,
        detail: toolCalls.length ? `调用：${toolCalls.join(", ")}` : "生成回答",
      });
      continue;
    }
    if (event.type === "tool.call.completed") {
      const retrieval = isRecord(payload.retrieval) ? payload.retrieval : null;
      const stageValues = retrieval && isRecord(retrieval.stages) ? retrieval.stages : null;
      const children = stageValues
        ? Object.entries(stageValues)
          .filter(([, value]) => typeof value === "number")
          .map(([stage, value]) => ({
            name: retrievalStageName(stage),
            at,
            elapsedMs: value as number,
          }))
        : undefined;
      const elapsed = typeof payload.elapsed_ms === "number"
        ? payload.elapsed_ms
        : retrieval && typeof retrieval.elapsed_ms === "number" ? retrieval.elapsed_ms : null;
      const rawCount = retrieval && typeof retrieval.raw_docs_count === "number"
        ? `原始 ${retrieval.raw_docs_count} 篇`
        : "";
      const selectedCount = retrieval && typeof retrieval.selected_docs_count === "number"
        ? `保留 ${retrieval.selected_docs_count} 篇`
        : "";
      actions.push({
        name: typeof payload.tool_name === "string" ? payload.tool_name : "工具调用",
        at,
        elapsedMs: elapsed,
        status: retrieval?.cache_hit === true ? "缓存命中" : undefined,
        detail: [rawCount, selectedCount].filter(Boolean).join(" · ") || undefined,
        children,
      });
    }
  }
  telemetry = {
    ...telemetry,
    lastRun: { ...telemetry.lastRun, traceRunId: trace.run_id, actions },
  };
  emit();
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function retrievalStageName(stage: string): string {
  const names: Record<string, string> = {
    search_ms: "混合检索",
    grading_ms: "文档评分",
    compression_ms: "上下文压缩",
    graph_ms: "知识图谱检索",
  };
  return names[stage] ?? stage;
}

export function recordRunSources(sources: Array<{ hit_chain?: string[] }>): void {
  const chain: string[] = [];
  for (const s of sources) {
    for (const h of s.hit_chain ?? []) {
      if (!chain.includes(h)) chain.push(h);
    }
  }
  telemetry = {
    ...telemetry,
    lastRun: {
      ...telemetry.lastRun,
      sourceCount: sources.length,
      hitChain: chain,
    },
  };
  emit();
}

export function recordRunTools(tools: string[]): void {
  telemetry = {
    ...telemetry,
    lastRun: { ...telemetry.lastRun, tools },
  };
  emit();
}

export function recordRunEnd(elapsedMs: number | null): void {
  telemetry = {
    ...telemetry,
    lastRun: { ...telemetry.lastRun, elapsedMs },
  };
  emit();
}

export function recordRunError(message: string): void {
  telemetry = {
    ...telemetry,
    lastRun: { ...telemetry.lastRun, error: message },
  };
  emit();
}

export function recordApiError(url: string, status: number): void {
  const entry: ApiErrorEntry = { url, status, at: Date.now() };
  telemetry = {
    ...telemetry,
    apiErrors: [...telemetry.apiErrors.slice(-(MAX_API_ERRORS - 1)), entry],
  };
  emit();
}

export function useDevTelemetry(): DevTelemetry {
  return useSyncExternalStore(
    (cb) => {
      listeners.add(cb);
      return () => listeners.delete(cb);
    },
    () => telemetry,
  );
}
