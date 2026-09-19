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
  route: string | null;
  llmCalls: number | null;
  rawDocsCount: number | null;
  selectedDocsCount: number | null;
  contextTokens: number | null;
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
    route: null,
    llmCalls: null,
    rawDocsCount: null,
    selectedDocsCount: null,
    contextTokens: null,
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
      route: null,
      llmCalls: null,
      rawDocsCount: null,
      selectedDocsCount: null,
      contextTokens: null,
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
      route: null,
      llmCalls: null,
      rawDocsCount: null,
      selectedDocsCount: null,
      contextTokens: null,
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
    lastRun: {
      ...telemetry.lastRun,
      traceRunId: trace.run_id,
      actions,
      route: "agent",
      llmCalls: actions.filter((action) => action.name.startsWith("LLM #")).length,
    },
  };
  emit();
}

export function recordFastRagTrace(trace: {
  route: "fast_rag" | "direct";
  total_ms: number;
  stages: Record<string, number>;
  llm_calls: number;
  raw_docs_count: number;
  selected_docs_count: number;
  context_tokens: number;
  relevant: boolean;
  routing?: {
    route: string;
    confidence: number;
    reasons: string[];
    signals: Record<string, number | boolean>;
  };
}): void {
  const now = Date.now();
  const names: Record<string, string> = {
    search_ms: "混合检索",
    gate_ms: "相关性判断",
    context_ms: "上下文构建",
    llm_ms: "LLM #1",
  };
  const actions: ActionTelemetry[] = Object.entries(trace.stages)
    .filter(([, elapsedMs]) => typeof elapsedMs === "number")
    .map(([stage, elapsedMs]) => ({
      name: names[stage] ?? stage,
      at: now,
      elapsedMs,
    }));
  if (trace.routing) {
    const routingMs = trace.routing.signals.routing_ms;
    actions.unshift({
      name: "智能路由",
      at: now,
      elapsedMs: typeof routingMs === "number" ? routingMs : null,
      detail: `${trace.routing.route} · ${Math.round(trace.routing.confidence * 100)}% · ${trace.routing.reasons.join(" / ")}`,
      children: Object.entries(trace.routing.signals)
        .filter(([key, value]) => key !== "routing_ms" && (typeof value === "number" || typeof value === "boolean"))
        .map(([key, value]) => ({ name: routingSignalName(key), at: now, elapsedMs: null, detail: typeof value === "number" ? `${Math.round(value * 100)}%` : String(value) })),
    });
  }
  telemetry = {
    ...telemetry,
    lastRun: {
      ...telemetry.lastRun,
      elapsedMs: trace.total_ms,
      actions,
      traceRunId: null,
      tools: [],
      route: trace.route,
      llmCalls: trace.llm_calls,
      rawDocsCount: trace.raw_docs_count,
      selectedDocsCount: trace.selected_docs_count,
      contextTokens: trace.context_tokens,
    },
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

function routingSignalName(signal: string): string {
  const names: Record<string, string> = {
    semantic: "语义命中", lexical: "关键词覆盖", rank: "候选排名",
    context: "会话关联", hit_count: "候选数量", dense_bm25_agreement: "Hybrid 一致",
    agent_intent: "Agent 意图", direct_intent: "直连意图",
    top1_score: "首条检索分", top3_mean: "前三平均分", top1_top2_gap: "首二分差",
    intent_direct: "直连原型意图", intent_fast_rag: "知识库原型意图",
    intent_agent: "工具原型意图",
  };
  return names[signal] ?? signal;
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
