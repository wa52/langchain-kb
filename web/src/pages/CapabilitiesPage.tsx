import { useCallback, useEffect, useState } from "react";

import { getCapabilities } from "../api/client";
import type { CapabilityCatalog, CapabilityMcpServer, CapabilityTool } from "../types/api";

const STATUS_LABEL: Record<CapabilityMcpServer["status"], string> = {
  ready: "可用",
  discovering: "发现中",
  degraded: "异常",
  not_started: "待发现",
  disabled: "已停用",
};

function Risk({ level }: { level: string }) {
  return <span className={`cap-risk cap-risk-${level}`}>{level === "low" ? "低风险" : level === "medium" ? "中风险" : level === "high" ? "高风险" : level === "critical" ? "严重风险" : level}</span>;
}

function ToolRow({ tool }: { tool: CapabilityTool }) {
  return (
    <article className={`capability-tool ${tool.enabled ? "" : "is-disabled"}`}>
      <div className="capability-tool-head">
        <div><strong>{tool.name}</strong><span className={`cap-source source-${tool.source}`}>{tool.source === "local" ? "本地工具" : tool.source === "mcp" ? `MCP · ${tool.server_id ?? "server"}` : "插件"}</span></div>
        <Risk level={tool.risk_level} />
      </div>
      {tool.description ? <p>{tool.description}</p> : null}
      <div className="capability-tool-foot">
        <div className="cap-tags">{tool.tags.map((tag) => <span key={tag}>{tag}</span>)}</div>
        <span>{tool.read_only ? "只读" : "可写"} · {tool.retryable ? "可重试" : "不自动重试"}</span>
      </div>
    </article>
  );
}

export function CapabilitiesPage({ onOpenSettings }: { onOpenSettings?: () => void }) {
  const [catalog, setCatalog] = useState<CapabilityCatalog | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setCatalog(await getCapabilities());
    } catch (reason) {
      setCatalog(null);
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);

  const tools = catalog?.tools ?? [];
  const servers = catalog?.mcp_servers ?? [];
  const nativeTools = tools.filter((tool) => tool.source !== "mcp");
  const mcpTools = tools.filter((tool) => tool.source === "mcp");

  return (
    <section className="page capabilities-page" aria-labelledby="capabilities-title">
      <div className="capabilities-heading">
        <div>
          <p className="capabilities-eyebrow">RUNTIME / CAPABILITY CATALOG</p>
          <h1 id="capabilities-title">能力目录</h1>
          <p className="muted">查看 Agent 当前已知工具与 MCP 发现状态。此页只读，不会连接 Server 或执行工具。</p>
        </div>
        <button type="button" className="secondary" disabled={loading} onClick={() => void refresh()}>{loading ? "刷新中…" : "刷新状态"}</button>
      </div>

      {loading ? <div className="capability-state" role="status"><span className="retrieval-spinner" />正在读取能力目录…</div> : null}
      {error ? <div className="capability-state error" role="alert"><strong>能力目录读取失败</strong><span>{error}</span><button className="secondary" type="button" onClick={() => void refresh()}>重试</button></div> : null}
      {!loading && !error && catalog ? <>
        <div className="capability-summary" aria-label="能力统计">
          <div><span>已注册工具</span><strong>{catalog.summary.tools}</strong></div>
          <div><span>MCP Server</span><strong>{catalog.summary.mcp_servers}</strong></div>
          <div><span>可用</span><strong>{catalog.summary.ready}</strong></div>
          <div className={catalog.summary.degraded ? "attention" : ""}><span>异常</span><strong>{catalog.summary.degraded}</strong></div>
        </div>

        {tools.length === 0 && servers.length === 0 ? (
          <div className="capability-state empty"><strong>目录暂时为空</strong><span>运行时插件还未完成注册，或尚未配置 MCP Server。</span></div>
        ) : <div className="capability-layout">
          <div className="capability-tools-column">
            <div className="capability-section-title"><div><h2>Agent 工具</h2><span>已注册的可调用能力</span></div><span className="mono">{tools.length} ITEMS</span></div>
            {nativeTools.length ? <><h3 className="capability-subtitle">内置与插件</h3><div className="capability-tool-list">{nativeTools.map((tool) => <ToolRow key={`${tool.source}:${tool.name}`} tool={tool} />)}</div></> : null}
            {mcpTools.length ? <><h3 className="capability-subtitle">MCP 工具</h3><div className="capability-tool-list">{mcpTools.map((tool) => <ToolRow key={`${tool.server_id}:${tool.name}`} tool={tool} />)}</div></> : null}
            {!tools.length ? <p className="muted capability-empty-tools">尚无工具注册。服务完成启动或 Agent 首次发现后，可刷新查看。</p> : null}
          </div>

          <aside className="capability-servers-column">
            <div className="capability-section-title"><div><h2>MCP Server</h2><span>连接发现状态</span></div><span className="mono">{servers.length} SERVERS</span></div>
            {servers.length ? <div className="capability-server-list">{servers.map((server) => (
              <article className={`capability-server status-${server.status}`} key={server.name}>
                <span className="capability-server-light" aria-hidden="true" />
                <div><strong>{server.name}</strong><span>{server.type} · {STATUS_LABEL[server.status]}</span></div>
                <code>{server.status.replace("_", " ").toUpperCase()}</code>
              </article>
            ))}</div> : <div className="capability-server-empty"><span aria-hidden="true">⌁</span><p>还没有配置外部能力。</p>{onOpenSettings ? <button type="button" className="link-btn" onClick={onOpenSettings}>前往设置</button> : null}</div>}
            <p className="capability-note">“待发现”表示当前进程尚未为该 Server 启动工具发现；打开本页不会额外发起连接。</p>
          </aside>
        </div>}
      </> : null}
    </section>
  );
}
