import { StatusDot as StatusDotSafe } from "../components/StatusDot";
import type { SystemStatus } from "../types/api";

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

export function StatusPage({ status }: { status: SystemStatus | null }) {
  const components = status?.components ?? {};
  const issues = Object.values(components).filter(
    (c) => c.state === "error" || c.state === "degraded" || c.state === "pending",
  );

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

      <p className="muted" style={{ fontSize: 13 }}>
        完整诊断（深度探测与修复建议）将在后续版本提供；当前为轻量状态展示，只读。
      </p>
    </div>
  );
}
