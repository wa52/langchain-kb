import { useState, type FormEvent } from "react";

import { getAgentTrace } from "../api/client";
import type { AgentTrace, TraceEvent } from "../types/api";

const EVENT_LABEL: Record<string, string> = {
  "agent.run.started": "运行开始",
  "agent.run.completed": "运行完成",
  "selector.started": "工具筛选开始",
  "selector.completed": "工具筛选完成",
  "llm.request": "模型请求",
  "llm.response": "模型响应",
  "llm.tool_calls": "模型工具调用意图",
  "tool.call.started": "工具开始",
  "tool.call.completed": "工具完成",
  "tool.call.failed": "工具失败",
  "approval.requested": "等待审批",
  "approval.resolved": "审批完成",
  "verification.completed": "结果验证",
  "mcp.catalog": "MCP 能力目录",
};

const PRIVATE_REASONING_KEYS = new Set([
  "reasoning", "reasoning_content", "thinking", "chain_of_thought", "system_prompt", "messages",
  "prompt", "input_messages",
]);

function safePayload(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(safePayload);
  if (!value || typeof value !== "object") return value;
  return Object.fromEntries(Object.entries(value as Record<string, unknown>)
    .filter(([key]) => !PRIVATE_REASONING_KEYS.has(key.toLowerCase()))
    .map(([key, item]) => [
      key,
      /(?:api[_-]?key|token|secret|password|authorization|cookie)/i.test(key)
        ? "[已隐藏]"
        : safePayload(item),
    ]));
}

function formatDuration(payload: Record<string, unknown>): string | null {
  for (const field of ["duration_ms", "elapsed_ms", "waited_ms", "total_ms"]) {
    const value = payload[field];
    if (typeof value === "number" && Number.isFinite(value)) return `${value.toFixed(value < 10 ? 1 : 0)} ms`;
  }
  return null;
}

function eventHeading(event: TraceEvent): string {
  const payload = event.payload;
  const action = payload.tool_name ?? payload.model ?? payload.domain;
  const label = EVENT_LABEL[event.type] ?? event.type;
  return action == null ? label : `${label} · ${String(action)}`;
}

function EventCard({ event, index }: { event: TraceEvent; index: number }) {
  const payload = safePayload(event.payload) as Record<string, unknown>;
  const duration = formatDuration(event.payload);
  const failed = event.type.endsWith("failed") || payload.success === false;
  return (
    <article className={`trace-event ${failed ? "trace-event-failed" : ""}`}>
      <span className="trace-event-index">{String(index + 1).padStart(2, "0")}</span>
      <span className="trace-event-mark" aria-hidden="true" />
      <div className="trace-event-content">
        <div className="trace-event-heading">
          <strong>{eventHeading(event)}</strong>
          <span className="trace-event-time">{new Date(event.created_at).toLocaleTimeString()}</span>
        </div>
        <div className="trace-event-meta">
          <code>{event.type}</code>
          {duration ? <span>{duration}</span> : null}
          {typeof payload.success === "boolean" ? <span className={payload.success ? "trace-success" : "trace-failed"}>{payload.success ? "成功" : "失败"}</span> : null}
          {typeof payload.retry_count === "number" && payload.retry_count > 0 ? <span>重试 {payload.retry_count} 次</span> : null}
        </div>
        <details className="trace-event-data">
          <summary>查看可观测数据</summary>
          <pre>{JSON.stringify(payload, null, 2)}</pre>
        </details>
      </div>
    </article>
  );
}

function TraceDetails({ trace }: { trace: AgentTrace }) {
  return (
    <div className="trace-result">
      <header className="trace-run-header">
        <div>
          <p className="trace-kicker">COMPLETED AGENT RUN</p>
          <h2>执行链路</h2>
          <code className="trace-run-id">{trace.run_id}</code>
        </div>
        <div className="trace-run-counts">
          <span><strong>{trace.events.length}</strong> 个事件</span>
          <span><strong>{trace.llm_calls?.length ?? 0}</strong> 次模型调用</span>
          <span><strong>{trace.tool_calls?.length ?? 0}</strong> 次工具调用</span>
        </div>
      </header>
      <section className="trace-query">
        <span>用户请求</span>
        <p>{trace.query || "未记录用户请求"}</p>
      </section>
      {trace.selected_tools?.length ? (
        <section className="trace-selected-tools">
          <span>筛选后的工具</span>
          <div>{trace.selected_tools.map((name) => <code key={name}>{name}</code>)}</div>
        </section>
      ) : null}
      {trace.events.length ? (
        <div className="trace-timeline" aria-label="按发生顺序排列的 Agent 动作">
          {trace.events.map((event, index) => <EventCard event={event} index={index} key={`${event.created_at}:${index}`} />)}
        </div>
      ) : <div className="trace-state empty"><strong>此运行没有动作事件</strong><span>Trace 里尚未记录可显示的执行步骤。</span></div>}
      <p className="trace-boundary-note">此处展示可观测的请求、工具动作与结果元数据，不包含模型隐藏思维过程。</p>
    </div>
  );
}

export function TraceViewerPage() {
  const [runIdInput, setRunIdInput] = useState("");
  const [trace, setTrace] = useState<AgentTrace | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searched, setSearched] = useState(false);

  async function loadTrace(runId: string): Promise<void> {
    if (!runId) return;
    setLoading(true);
    setError(null);
    setTrace(null);
    setSearched(true);
    try {
      setTrace(await getAgentTrace(runId));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setLoading(false);
    }
  }

  function lookup(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    void loadTrace(runIdInput.trim());
  }

  return (
    <section className="page trace-page" aria-labelledby="trace-title">
      <div className="trace-page-heading">
        <div>
          <p className="trace-kicker">OBSERVABILITY / RUN INSPECTOR</p>
          <h1 id="trace-title">Agent Trace</h1>
          <p className="muted">输入一次已完成回答的 run_id，查看模型调用、工具动作和耗时。</p>
        </div>
      </div>
      <form className="trace-lookup" onSubmit={(event) => void lookup(event)}>
        <label htmlFor="trace-run-id">Run ID</label>
        <input id="trace-run-id" value={runIdInput} onChange={(event) => setRunIdInput(event.target.value)} placeholder="粘贴 run_id" autoComplete="off" spellCheck={false} />
        <button type="submit" className="primary" disabled={loading || !runIdInput.trim()}>{loading ? "查询中…" : "查询 Trace"}</button>
      </form>

      {loading ? <div className="trace-state" role="status"><span className="retrieval-spinner" />正在读取这次运行的 Trace…</div> : null}
      {error ? <div className="trace-state error" role="alert"><strong>Trace 查询失败</strong><span>{error}</span><button type="button" className="secondary" disabled={loading} onClick={() => void loadTrace(runIdInput.trim())}>重试</button></div> : null}
      {!loading && !error && searched && !trace ? <div className="trace-state empty"><strong>没有找到这条运行记录</strong><span>Trace 仅在服务进程内暂存。请确认 run_id 正确，并且对应服务实例仍保留该记录。</span></div> : null}
      {!loading && trace ? <TraceDetails trace={trace} /> : null}
      {!loading && !error && !searched ? <div className="trace-state empty"><strong>输入 run_id 开始检查</strong><span>可从回答结束事件或开发者面板复制 run_id。页面不会列出或读取其他会话记录。</span></div> : null}
    </section>
  );
}
