import { useState } from "react";

import { StatusDot as StatusDotSafe } from "../components/StatusDot";
import { useDiagnostics } from "../hooks/useDiagnostics";
import type { DiagnosticsCheck, SystemStatus } from "../types/api";

const STATE_LABEL: Record<string, string> = {
  ok: "正常",
  degraded: "降级",
  error: "错误",
  loading: "加载中",
  pending: "待启动",
};

function metric(name: string, value: string | number) {
  return (
    <span className="rail-item" title={name}>
      <span>{name}</span>
      <span className="mono">{value}</span>
    </span>
  );
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
    <div className={`issue ${check.status === "error" ? "error" : ""}`}>
      <p>
        <strong>{check.name}</strong>
        {check.error ? `：${check.error}` : check.detail ? `：${check.detail}` : ""}
      </p>
      {check.fix ? <p className="fix-hint">建议：{check.fix}</p> : null}
      {check.repairable && !repaired ? (
        <button type="button" className="repair-btn" onClick={() => void handleRepair()}>
          {confirming ? "确认修复?" : "修复"}
        </button>
      ) : null}
      {repaired ? <p className="fix-hint">已修复，可重新运行完整诊断验证。</p> : null}
    </div>
  );
}

export function StatusPage({ status }: { status: SystemStatus | null }) {
  const { task, running, error: diagError, run, repair } = useDiagnostics();
  const [repairNote, setRepairNote] = useState<string | null>(null);

  const components = status?.components ?? {};
  const issues = Object.values(components).filter(
    (c) => c.state === "error" || c.state === "degraded" || c.state === "pending",
  );

  const result = task?.status === "done" ? task.result : null;
  const failedChecks = (result?.checks ?? []).filter((c) => !c.ok);

  async function handleRepair(name: string): Promise<boolean> {
    const ok = await repair(name);
    setRepairNote(ok ? `${name} 已修复` : `${name} 修复失败或不可修复`);
    return ok;
  }

  return (
    <div className="page">
      <div className="card">
        <h2>整体状态</h2>
        <p style={{ display: "flex", gap: 12, alignItems: "center" }}>
          <strong>{STATE_LABEL[status?.status ?? "pending"] ?? status?.status}</strong>
          <span className="muted">
            索引版本 {status?.index_version ?? "—"} · 运行 {Math.round(status?.uptime ?? 0)}s
          </span>
        </p>
        <div className="sys-rail" style={{ marginTop: 12, cursor: "default" }}>
          {Object.values(components).map((c) => (
            <span key={c.name} className="rail-item" title={c.detail ?? c.name}>
              <StatusDotSafe state={c.state} />
              <span>{c.name}</span>
            </span>
          ))}
        </div>
      </div>

      <div className="card">
        <h2>关键指标</h2>
        <div className="sys-rail" style={{ cursor: "default", gap: 18 }}>
          {metric("chunks", status?.vector_count ?? "—")}
          {metric("bm25", status?.bm25_chunks ?? "—")}
          {metric("entities", status?.entity_count ?? "—")}
        </div>
      </div>

      <div className="card">
        <h2>问题</h2>
        {status === null ? (
          <div className="issue error">
            <p>无法读取状态：状态服务不可用。</p>
          </div>
        ) : issues.length === 0 ? (
          <p className="muted">当前没有发现异常。</p>
        ) : (
          issues.map((c) => (
            <div key={c.name} className={`issue ${c.state === "error" ? "error" : ""}`}>
              <p>
                <strong>{c.name}</strong> · {c.state}
                {c.error ? `：${c.error}` : c.detail ? `：${c.detail}` : ""}
              </p>
            </div>
          ))
        )}
      </div>

      <div className="card">
        <h2>完整诊断</h2>
        <button
          type="button"
          className="primary"
          onClick={() => {
            setRepairNote(null);
            void run();
          }}
          disabled={running}
        >
          {running ? "诊断中…" : "运行完整诊断"}
        </button>
        <p className="muted" style={{ marginTop: 10, fontSize: 13 }}>
          完整诊断会逐一探测各组件（可能加载模型，耗时较长），只读；修复动作仅在失败项中显式确认后执行。
        </p>

        {diagError ? (
          <p className="msg-error" role="alert" style={{ marginTop: 10 }}>
            {diagError}
          </p>
        ) : null}
        {repairNote ? (
          <p className="muted" style={{ marginTop: 10, fontSize: 13 }}>
            {repairNote}
          </p>
        ) : null}

        {result ? (
          <div style={{ marginTop: 12 }}>
            <p className="muted" style={{ fontSize: 13 }}>
              结果：{result.summary.total} 项，通过 {result.summary.ok}，失败{" "}
              {result.summary.failed}
            </p>
            {failedChecks.length > 0 ? (
              <div style={{ marginTop: 10 }}>
                {failedChecks.map((c) => (
                  <IssueRow key={c.name} check={c} onRepair={handleRepair} />
                ))}
              </div>
            ) : (
              <p className="muted" style={{ marginTop: 8, fontSize: 13 }}>
                所有检查通过。
              </p>
            )}
          </div>
        ) : null}
      </div>
    </div>
  );
}
