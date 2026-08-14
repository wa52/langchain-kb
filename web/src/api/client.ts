import type {
  DiagnosticsTaskStatus,
  IndexTask,
  KnowledgeStats,
  SessionDetail,
  SessionSummary,
  SourceItem,
  TaskStatus,
  UploadTasks,
} from "../types/api";

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

export async function listSessions(): Promise<SessionSummary[]> {
  const resp = await fetch("/api/v1/sessions", {
    headers: { Accept: "application/json" },
  });
  if (!resp.ok) throw new Error(`会话列表请求失败 (${resp.status})`);
  const data = (await resp.json()) as { sessions: SessionSummary[] };
  return data.sessions ?? [];
}

export async function getSession(id: string): Promise<SessionDetail> {
  const resp = await fetch(`/api/v1/sessions/${encodeURIComponent(id)}`, {
    headers: { Accept: "application/json" },
  });
  if (!resp.ok) throw new Error(`会话读取失败 (${resp.status})`);
  return (await resp.json()) as SessionDetail;
}

export async function deleteSession(id: string): Promise<void> {
  const resp = await fetch(`/api/v1/sessions/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
  if (!resp.ok && resp.status !== 204) {
    throw new Error(`会话删除失败 (${resp.status})`);
  }
}

async function readError(resp: Response, fallback: string): Promise<string> {
  let detail = fallback;
  try {
    const body = await resp.json();
    detail = (body?.detail || body?.error || detail) as string;
  } catch {
    /* keep fallback */
  }
  return detail;
}

export async function getKnowledgeStats(): Promise<KnowledgeStats> {
  const resp = await fetch("/api/v1/knowledge/stats", {
    headers: { Accept: "application/json" },
  });
  if (!resp.ok) throw new Error(`知识库统计请求失败 (${resp.status})`);
  return (await resp.json()) as KnowledgeStats;
}

export async function indexPath(path: string): Promise<IndexTask> {
  const resp = await fetch("/api/v1/documents/index", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path }),
  });
  if (!resp.ok) {
    throw new Error(await readError(resp, `索引请求失败 (${resp.status})`));
  }
  return (await resp.json()) as IndexTask;
}

export async function uploadFiles(files: File[]): Promise<UploadTasks> {
  const form = new FormData();
  for (const f of files) form.append("files", f);
  const resp = await fetch("/api/v1/documents/upload", {
    method: "POST",
    body: form,
  });
  if (!resp.ok) {
    throw new Error(await readError(resp, `上传失败 (${resp.status})`));
  }
  return (await resp.json()) as UploadTasks;
}

export async function getTaskStatus(taskId: string): Promise<TaskStatus> {
  const resp = await fetch(`/api/v1/index/tasks/${encodeURIComponent(taskId)}`, {
    headers: { Accept: "application/json" },
  });
  if (!resp.ok) throw new Error(`任务查询失败 (${resp.status})`);
  return (await resp.json()) as TaskStatus;
}

export async function startDiagnostics(): Promise<{ task_id: string; status: string }> {
  const resp = await fetch("/api/v1/diagnostics", { method: "POST" });
  if (!resp.ok) {
    throw new Error(await readError(resp, `诊断请求失败 (${resp.status})`));
  }
  return (await resp.json()) as { task_id: string; status: string };
}

export async function getDiagnostics(
  taskId: string,
): Promise<DiagnosticsTaskStatus> {
  const resp = await fetch(`/api/v1/diagnostics/tasks/${encodeURIComponent(taskId)}`, {
    headers: { Accept: "application/json" },
  });
  if (!resp.ok) throw new Error(`诊断查询失败 (${resp.status})`);
  return (await resp.json()) as DiagnosticsTaskStatus;
}

export async function repairDiagnostics(
  taskId: string,
  name: string,
): Promise<{ repaired: boolean }> {
  const resp = await fetch("/api/v1/diagnostics/repair", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ task_id: taskId, name }),
  });
  if (!resp.ok) {
    throw new Error(await readError(resp, `修复请求失败 (${resp.status})`));
  }
  return (await resp.json()) as { repaired: boolean };
}
