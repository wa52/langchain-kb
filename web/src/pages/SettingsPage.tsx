import type { SystemStatus } from "../types/api";

export function SettingsPage({ status }: { status: SystemStatus | null }) {
  const components = status?.components ?? {};

  return (
    <div className="page">
      <div className="card">
        <h2>设置（只读）</h2>
        <dl className="kv">
          <dt>embedding</dt>
          <dd>{components.embedding?.state ?? "—"}</dd>
          <dt>llm</dt>
          <dd>{components.llm?.state ?? "—"}</dd>
          <dt>vector_store</dt>
          <dd>{components.vector_store?.state ?? "—"}</dd>
          <dt>graph</dt>
          <dd>{components.graph?.state ?? "—"}</dd>
        </dl>
        <p className="muted" style={{ marginTop: 12, fontSize: 13 }}>
          第一阶段为只读设置：不显示任何密钥，也不在界面中编辑配置。完整配置状态将在后续版本展示。
        </p>
        <p className="muted" style={{ fontSize: 13 }}>
          配置变更请编辑数据目录下的 <span className="mono">.env</span> 后重启服务。
        </p>
      </div>
    </div>
  );
}
