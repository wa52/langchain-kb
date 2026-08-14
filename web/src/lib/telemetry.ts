import { useSyncExternalStore } from "react";

export interface RunTelemetry {
  startedAt: number | null;
  elapsedMs: number | null;
  sourceCount: number | null;
  hitChain: string[];
  tools: string[];
  error: string | null;
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
    },
    apiErrors: [],
  };
  emit();
}

export function recordStreamEvent(type: string): void {
  telemetry = {
    ...telemetry,
    streamEvents: {
      ...telemetry.streamEvents,
      [type]: (telemetry.streamEvents[type] ?? 0) + 1,
    },
    lastStreamEvent: type,
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
    },
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
