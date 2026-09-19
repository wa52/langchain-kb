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
  let previous: number | null = null;
  const actions = (trace.events ?? []).map((event) => {
    const parsed = Date.parse(event.created_at);
    const at = Number.isFinite(parsed) ? parsed : Date.now();
    const payload = event.payload ?? {};
    const status = typeof payload.status === "string" ? payload.status : undefined;
    const detail = typeof payload.tool_name === "string"
      ? payload.tool_name
      : typeof payload.error === "string" ? payload.error : undefined;
    const action: ActionTelemetry = {
      name: event.type,
      at,
      elapsedMs: previous == null ? null : Math.max(0, at - previous),
      status,
      detail,
    };
    previous = at;
    return action;
  });
  telemetry = {
    ...telemetry,
    lastRun: { ...telemetry.lastRun, traceRunId: trace.run_id, actions },
  };
  emit();
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
