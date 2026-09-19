import { useCallback, useEffect, useState } from "react";

import { apiFetch } from "../api/client";
import { resetDevTelemetry, useDevTelemetry } from "../lib/telemetry";

function fmtMs(ms: number | null): string {
  return ms == null ? "—" : `${ms.toFixed(0)} ms`;
}

function fmtTime(ts: number): string {
  return new Date(ts).toLocaleTimeString();
}

export function DeveloperPane() {
  const t = useDevTelemetry();
  const [statusText, setStatusText] = useState<string>("");
  const [statusError, setStatusError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const refreshStatus = useCallback(async () => {
    setLoading(true);
    setStatusError(null);
    try {
      const resp = await apiFetch("/api/v1/status", {
        headers: { Accept: "application/json" },
      });
      if (!resp.ok) {
        setStatusError(`状态请求失败 (${resp.status})`);
        setStatusText("");
        return;
      }
      const data = await resp.json();
      setStatusText(JSON.stringify(data, null, 2));
    } catch (err) {
      setStatusError(err instanceof Error ? err.message : String(err));
      setStatusText("");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refreshStatus();
  }, [refreshStatus]);

  const eventEntries = Object.entries(t.streamEvents).sort(([a], [b]) =>
    a.localeCompare(b),
  );
  const run = t.lastRun;

  return (
    <aside className="dev-pane" aria-label="开发者模式">
      <div className="dev-pane-head">
        <strong>开发者模式</strong>
        <button
          type="button"
          className="dev-pane-action"
          onClick={() => {
            resetDevTelemetry();
            void refreshStatus();
          }}
        >
          清空
        </button>
      </div>

      <section className="dev-section">
        <h4>SSE 流状态</h4>
        {eventEntries.length === 0 ? (
          <p className="dev-muted">暂无事件</p>
        ) : (
          <ul className="dev-list">
            {eventEntries.map(([type, count]) => (
              <li key={type}>
                <code>{type}</code>
                <span className="dev-count">×{count}</span>
              </li>
            ))}
          </ul>
        )}
        <p className="dev-muted">
          最近事件：<code>{t.lastStreamEvent ?? "—"}</code>
        </p>
      </section>

      <section className="dev-section">
        <h4>动作耗时</h4>
        {run.actions.length === 0 ? (
          <p className="dev-muted">暂无动作记录</p>
        ) : (
          <ol className="dev-action-list">
            {run.actions.map((action, index) => (
              <li key={`${action.at}-${index}`}>
                <span className="dev-action-index">{index + 1}</span>
                <code>{action.name}</code>
                <span className="dev-count">{fmtMs(action.elapsedMs)}</span>
                {action.status ? <span className="dev-muted">{action.status}</span> : null}
                {action.detail ? <span className="dev-muted">{action.detail}</span> : null}
                {action.children?.length ? (
                  <ul className="dev-action-children">
                    {action.children.map((child, childIndex) => (
                      <li key={`${child.name}-${childIndex}`}>
                        <code>{child.name}</code>
                        <span className="dev-count">{fmtMs(child.elapsedMs)}</span>
                        {child.detail ? <span className="dev-muted">{child.detail}</span> : null}
                      </li>
                    ))}
                  </ul>
                ) : null}
              </li>
            ))}
          </ol>
        )}
        {run.traceRunId ? <p className="dev-muted">run_id：<code>{run.traceRunId}</code></p> : null}
      </section>

      <section className="dev-section">
        <h4>最近一次回答</h4>
        <ul className="dev-list">
          <li>
            耗时 <span className="dev-count">{fmtMs(run.elapsedMs)}</span>
          </li>
          <li>
            路径 <span className="dev-count">{run.route ?? "—"}</span>
          </li>
          <li>
            LLM 调用 <span className="dev-count">{run.llmCalls ?? "—"}</span>
          </li>
          <li>
            文档 <span className="dev-count">
              {run.rawDocsCount == null ? "—" : `${run.rawDocsCount} → ${run.selectedDocsCount ?? 0}`}
            </span>
          </li>
          <li>
            Context <span className="dev-count">{run.contextTokens == null ? "—" : `${run.contextTokens} tokens`}</span>
          </li>
          <li>
            来源数 <span className="dev-count">{run.sourceCount ?? "—"}</span>
          </li>
          <li>
            检索链路{" "}
            <span className="dev-count">
              {run.hitChain.length ? run.hitChain.join(" / ") : "—"}
            </span>
          </li>
          <li>
            工具调用{" "}
            <span className="dev-count">
              {run.tools.length ? run.tools.join(", ") : "—"}
            </span>
          </li>
        </ul>
        {run.error ? <p className="dev-error">{run.error}</p> : null}
      </section>

      <section className="dev-section">
        <h4>API 错误摘要</h4>
        {t.apiErrors.length === 0 ? (
          <p className="dev-muted">暂无错误</p>
        ) : (
          <ul className="dev-list">
            {t.apiErrors.map((e, i) => (
              <li key={`${e.at}-${i}`}>
                <code>{e.url}</code>
                <span className="dev-count dev-error">{e.status}</span>
                <span className="dev-muted">{fmtTime(e.at)}</span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="dev-section">
        <h4>原始状态 JSON</h4>
        <button
          type="button"
          className="dev-pane-action"
          onClick={() => void refreshStatus()}
          disabled={loading}
        >
          {loading ? "加载中…" : "刷新"}
        </button>
        {statusError ? <p className="dev-error">{statusError}</p> : null}
        <pre className="dev-json">{statusText || "—"}</pre>
      </section>
    </aside>
  );
}
