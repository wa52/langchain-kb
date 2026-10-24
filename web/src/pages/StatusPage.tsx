import { useState } from "react";

import { StatusDot } from "../components/StatusDot";
import { useDiagnostics } from "../hooks/useDiagnostics";
import type { DiagnosticsCheck, SystemStatus } from "../types/api";

const STATE_LABEL: Record<string, string> = {
  ok: "服务运行中",
  ready: "可用",
  degraded: "部分可用",
  error: "异常",
  loading: "加载中",
  pending: "待就绪",
  disabled: "未启用",
};

const COMPONENT_LABEL: Record<string, string> = {
  embedding: "向量模型",
  llm: "语言模型",
  vector: "向量索引",
  vector_store: "向量索引",
  bm25: "关键词索引",
  graph: "知识图谱",
  agent: "Agent",
  index: "索引任务",
};

function componentDetail(key: string, state: string, detail?: string | null, error?: string | null): string | null {
  if (error) return error;
  if (key === "vector_store" && state === "ready") return "存储已连接";
  return detail ?? null;
}

interface IssueRowProps {
  check: DiagnosticsCheck;
  onRepair: (name: string) => Promise<boolean>;
}

function IssueRow({ check, onRepair }: IssueRowProps) {
  const [confirming, setConfirming] = useState(false);
  const [repaired, setRepaired] = useState(false);

  async function handleRepair(): Promise<void> {
    if (!confirming) {
      setConfirming(true);
      return;
    }
    setConfirming(false);
    const ok = await onRepair(check.name);
    if (ok) setRepaired(true);
  }

  return (
    <div className={`status-issue ${check.status === "error" ? "error" : ""}`}>
      <div>
        <strong>{COMPONENT_LABEL[check.name] ?? check.name}</strong>
        <p>{check.error || check.detail || "检查未通过"}</p>
        {check.fix ? <p className="status-fix-hint">建议：{check.fix}</p> : null}
        {repaired ? <p className="status-fix-hint">已执行修复，请重新运行诊断验证。</p> : null}
      </div>
      {check.repairable && !repaired ? (
        <button type="button" className="status-repair ui-hint" data-hint={confirming ? "确认执行此项修复操作" : "查看此项修复的确认步骤"} aria-label={`${confirming ? "确认修复" : "修复"} ${COMPONENT_LABEL[check.name] ?? check.name}`} onClick={() => void handleRepair()}>
          <span aria-hidden="true">↻</span>{confirming ? "确认修复" : "修复"}
        </button>
      ) : null}
    </div>
  );
}

export function StatusPage({ status, statusError }: { status: SystemStatus | null; statusError?: string | null }) {
  const { task, running, error: diagError, run, repair } = useDiagnostics();
  const [repairNote, setRepairNote] = useState<string | null>(null);

  const components = Object.entries(status?.components ?? {});
  const issues = components.filter(
    ([, component]) => component.state === "error" || component.state === "degraded" || component.state === "pending",
  );

  const result = task?.status === "done" ? task.result : null;
  const failedChecks = (result?.checks ?? []).filter((c) => !c.ok);
  const overallState = status?.status ?? (statusError ? "error" : "loading");
  const overallLabel = status ? (STATE_LABEL[overallState] ?? "状态未知") : statusError ? "服务未连接" : "正在读取状态";

  async function handleRepair(name: string): Promise<boolean> {
    const ok = await repair(name);
    setRepairNote(ok ? `${name} 已修复` : `${name} 修复失败或不可修复`);
    return ok;
  }

  return (
    <div className="status-page">
      <header className="status-page-head">
        <span className="status-eyebrow">SYSTEM / STATUS</span>
        <h1>服务状态</h1>
        <p>先看当前可用性，再查看组件与诊断结果。</p>
      </header>

      <section className={`status-overview state-${overallState}`} aria-label="总体状态" role="status">
        <div className="status-overview-main">
          <span className="status-overview-icon" aria-hidden="true"><StatusDot state={overallState} /></span>
          <div>
            <span className="status-overview-kicker">总体可用性</span>
            <h2>{overallLabel}</h2>
            <p>{status
              ? "以下状态来自各组件的运行报告，不等同于索引完整性校验。"
              : statusError
                ? "当前无法读取组件状态。请检查服务是否启动及网络连接。"
                : "正在获取组件状态，请稍候。"}</p>
          </div>
        </div>
        {status ? (
          <div className="status-overview-meta">
            <span>索引版本 <strong>{status.index_version}</strong></span>
            <span>运行时间 <strong>{Math.round(status.uptime)} 秒</strong></span>
          </div>
        ) : null}
      </section>

      <section className="status-section" aria-labelledby="status-components-title">
        <div className="status-section-head"><h2 id="status-components-title">组件</h2><span>{components.length} 项</span></div>
        {components.length ? (
          <ul className="status-components">
            {components.map(([key, component]) => {
              const detail = componentDetail(key, component.state, component.detail, component.error);
              return <li key={key}>
                <div className="status-component-name"><StatusDot state={component.state} /><strong>{COMPONENT_LABEL[key] ?? component.name}</strong></div>
                <span className="status-component-state">{STATE_LABEL[component.state] ?? "状态未知"}</span>
                {detail ? <p>{detail}</p> : null}
              </li>;
            })}
          </ul>
        ) : <p className="status-no-data">{statusError ? "连接恢复后会显示组件状态。" : "等待组件状态…"}</p>}
      </section>

      <section className="status-section" aria-labelledby="status-metrics-title">
        <div className="status-section-head"><h2 id="status-metrics-title">关键指标</h2></div>
        <dl className="status-metrics">
          <div><dt>知识片段</dt><dd>{status?.vector_count.toLocaleString() ?? "—"}</dd></div>
          <div><dt>BM25 条目</dt><dd>{status?.bm25_chunks?.toLocaleString() ?? "—"}</dd></div>
          <div><dt>图谱实体</dt><dd>{status?.entity_count.toLocaleString() ?? "—"}</dd></div>
        </dl>
      </section>

      <div className="status-detail-grid">
        <section className="status-section" aria-labelledby="status-issues-title">
          <div className="status-section-head"><h2 id="status-issues-title">需要关注</h2><span>{issues.length} 项</span></div>
          {status === null ? (
            <p className="status-no-data">{statusError ? "服务未连接，暂时无法判断组件问题。" : "状态读取中…"}</p>
          ) : issues.length === 0 ? (
            <p className="status-no-data">组件状态未报告异常；这不代表数据索引已通过完整性校验。</p>
          ) : (
            <ul className="status-issue-list">{issues.map(([key, component]) => (
              <li key={key} className={component.state}>
                <strong>{COMPONENT_LABEL[key] ?? component.name}</strong>
                <span>{STATE_LABEL[component.state] ?? "状态未知"}</span>
                {componentDetail(key, component.state, component.detail, component.error) ? <p>{componentDetail(key, component.state, component.detail, component.error)}</p> : null}
              </li>
            ))}</ul>
          )}
        </section>

        <section className="status-section status-diagnostics" aria-labelledby="status-diagnostics-title">
          <div className="status-section-head"><h2 id="status-diagnostics-title">完整诊断</h2></div>
          <p>逐项探测服务组件，可能加载模型并耗时较长。诊断只读；修复需在失败项中再次确认。</p>
          <button
            type="button"
            className="primary ui-hint"
            data-hint="执行只读的组件诊断，不会自动修复"
            onClick={() => { setRepairNote(null); void run(); }}
            disabled={running}
          ><span aria-hidden="true">⌕</span>{running ? "诊断中…" : "运行完整诊断"}</button>
          {diagError ? <p className="msg-error" role="alert">{diagError}</p> : null}
          {repairNote ? <p className="status-repair-note" role="status">{repairNote}</p> : null}
          {result ? (
            <div className="status-diagnostic-result">
              <p>检查 {result.summary.total} 项 · 通过 {result.summary.ok} · 失败 {result.summary.failed}</p>
              {failedChecks.length ? failedChecks.map((check) => (
                <IssueRow key={check.name} check={check} onRepair={handleRepair} />
              )) : <p className="status-no-data">本次组件诊断全部通过。</p>}
            </div>
          ) : null}
        </section>
      </div>
    </div>
  );
}
