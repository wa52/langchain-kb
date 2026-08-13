import type { SourceItem } from "../types/api";

export interface StreamHandlers {
  onToken?: (text: string) => void;
  onSources?: (sources: SourceItem[]) => void;
  onEnd?: (sessionId: string, interrupted: boolean) => void;
  onError?: (message: string) => void;
}

export interface StreamPayload {
  query: string;
  session_id?: string | null;
}

function handleSseBlock(block: string, handlers: StreamHandlers): void {
  let eventType: string | null = null;
  let data: string | null = null;
  for (const raw of block.split("\n")) {
    const line = raw.replace(/\r$/, "");
    if (line.startsWith("event:")) {
      eventType = line.slice("event:".length).trim();
    } else if (line.startsWith("data:")) {
      data = line.slice("data:".length).trim();
    }
  }
  if (!eventType || data == null) return;
  let payload: unknown;
  try {
    payload = JSON.parse(data);
  } catch {
    payload = data;
  }
  switch (eventType) {
    case "token":
      handlers.onToken?.(typeof payload === "object" && payload && "text" in payload
        ? String((payload as { text: string }).text)
        : String(payload ?? ""));
      break;
    case "sources":
      if (typeof payload === "object" && payload && "sources" in payload) {
        handlers.onSources?.((payload as { sources: SourceItem[] }).sources ?? []);
      }
      break;
    case "message_end":
      if (typeof payload === "object" && payload && "session_id" in payload) {
        const end = payload as { session_id: string; interrupted?: boolean };
        handlers.onEnd?.(end.session_id, Boolean(end.interrupted));
      }
      break;
    case "error":
      handlers.onError?.(typeof payload === "object" && payload && "error" in payload
        ? String((payload as { error: string }).error)
        : String(payload ?? "unknown error"));
      break;
    default:
      break;
  }
}

export async function streamChat(
  payload: StreamPayload,
  handlers: StreamHandlers,
  signal: AbortSignal,
): Promise<void> {
  const resp = await fetch("/api/v1/chat/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    signal,
  });
  if (!resp.ok || !resp.body) {
    let detail = `请求失败 (${resp.status})`;
    try {
      const body = await resp.json();
      detail = (body?.detail || body?.error || detail) as string;
    } catch {
      /* keep default detail */
    }
    throw new Error(detail);
  }

  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let idx = buffer.indexOf("\n\n");
    while (idx >= 0) {
      const block = buffer.slice(0, idx);
      buffer = buffer.slice(idx + 2);
      handleSseBlock(block, handlers);
      idx = buffer.indexOf("\n\n");
    }
  }
}
