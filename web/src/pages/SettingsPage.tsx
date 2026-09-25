import type { ReactNode } from "react";

import { useEffect, useState } from "react";
import { useSettings } from "../hooks/useSettings";
import { checkJevConnection, listLlmModels } from "../api/client";
import type { JevConnectionStatus } from "../api/client";
import type { AppSettings } from "../types/api";

function OnOff({ value }: { value: boolean }) {
  return <>{value ? "是" : "否"}</>;
}

function Row({ k, v }: { k: string; v: string | number | boolean }) {
  return (
    <>
      <dt>{k}</dt>
      <dd>{typeof v === "boolean" ? <OnOff value={v} /> : v}</dd>
    </>
  );
}

function Section({
  title,
  children,
  footer,
}: {
  title: string;
  children: ReactNode;
  footer?: ReactNode;
}) {
  return (
    <section className="card settings-section">
      <h3>{title}</h3>
      <dl className="kv">{children}</dl>
      {footer}
    </section>
  );
}

const PROVIDERS: Record<string, { label: string; baseUrl: string; models: string[] }> = {
  deepseek: { label: "DeepSeek", baseUrl: "https://api.deepseek.com", models: [] },
  openai: { label: "OpenAI", baseUrl: "https://api.openai.com/v1", models: [] },
  moonshot: { label: "Moonshot", baseUrl: "https://api.moonshot.cn/v1", models: [] },
  qwen: { label: "通义千问", baseUrl: "https://dashscope.aliyuncs.com/compatible-mode/v1", models: [] },
  zhipu: { label: "智谱", baseUrl: "https://open.bigmodel.cn/api/paas/v4", models: [] },
  siliconflow: { label: "SiliconFlow", baseUrl: "https://api.siliconflow.cn/v1", models: [] },
  ollama: { label: "Ollama（本地）", baseUrl: "http://127.0.0.1:11434/v1", models: [] },
};

export function SettingsPage({ onOpenTokenDialog }: { onOpenTokenDialog?: () => void }) {
  const {
    settings,
    error,
    actionError,
    saving,
    setGraphMode,
    setLlm,
    setMcpEnabled,
    setMcpServerEnabled,
    setJevApiKey,
  } = useSettings();
  const [provider, setProvider] = useState("deepseek");
  const [model, setModel] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [saved, setSaved] = useState(false);
  const [models, setModels] = useState<string[]>([]);
  const [loadingModels, setLoadingModels] = useState(false);
  const [modelError, setModelError] = useState<string | null>(null);
  const [jevKey, setJevKey] = useState("");
  const [jevCheck, setJevCheck] = useState<JevConnectionStatus | null>(null);
  const [checkingJev, setCheckingJev] = useState(false);
  const [jevCheckError, setJevCheckError] = useState<string | null>(null);

  useEffect(() => {
    if (!settings) return;
    setProvider(settings.llm_provider);
    setModel(settings.llm_model);
    setBaseUrl(settings.llm_api_base);
    setModels(settings.llm_model ? [settings.llm_model] : []);
  }, [settings]);

  // Load the provider's real model ids as soon as the provider/base URL is
  // known. The saved server-side key is used automatically; the explicit
  // button below is still useful immediately after entering a new key.
  useEffect(() => {
    if (!provider || !baseUrl) return;
    let cancelled = false;
    setLoadingModels(true);
    setModelError(null);
    listLlmModels({ provider, base_url: baseUrl })
      .then((next) => {
        if (cancelled) return;
        setModels(next);
        setModel((current) => next.includes(current) ? current : next[0] ?? current);
      })
      .catch((e) => {
        if (!cancelled) setModelError(e instanceof Error ? e.message : String(e));
      })
      .finally(() => {
        if (!cancelled) setLoadingModels(false);
      });
    return () => { cancelled = true; };
  }, [provider, baseUrl]);

  async function saveLlm() {
    const ok = await setLlm({ provider, model, base_url: baseUrl, ...(apiKey ? { api_key: apiKey } : {}) });
    if (ok) {
      setApiKey("");
      setSaved(true);
      window.setTimeout(() => setSaved(false), 3200);
    }
  }

  function chooseProvider(next: string) {
    setProvider(next);
    const preset = PROVIDERS[next];
    if (preset) {
      setBaseUrl(preset.baseUrl);
      setModel("");
      setModels(preset.models);
    } else {
      setModels([]);
    }
  }

  async function refreshModels() {
    setLoadingModels(true);
    setModelError(null);
    try {
      const next = await listLlmModels({ provider, base_url: baseUrl, ...(apiKey ? { api_key: apiKey } : {}) });
      setModels(next);
      setModel((current) => next.includes(current) ? current : next[0]);
    } catch (e) {
      setModelError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoadingModels(false);
    }
  }

  async function testJevConnection() {
    setCheckingJev(true);
    setJevCheckError(null);
    try {
      setJevCheck(await checkJevConnection());
    } catch (e) {
      setJevCheckError(e instanceof Error ? e.message : String(e));
    } finally {
      setCheckingJev(false);
    }
  }

  if (error) {
    return (
      <div className="page">
        <div className="card">
          <h2>设置（只读）</h2>
          <p className="chat-error" role="alert">
            配置读取失败：{error}
          </p>
          {onOpenTokenDialog ? (
            <button
              type="button"
              className="primary"
              onClick={onOpenTokenDialog}
              style={{ marginTop: 12 }}
            >
              输入访问令牌
            </button>
          ) : null}
        </div>
      </div>
    );
  }

  if (!settings) {
    return (
      <div className="page">
        <div className="card">
          <h2>设置（只读）</h2>
          <p className="muted">读取配置中…</p>
        </div>
      </div>
    );
  }

  const s: AppSettings = settings;

  return (
    <div className="page">
      <div className="card">
        <h2>设置</h2>
        <p className="muted" style={{ fontSize: 13 }}>
          API 密钥只用于保存，不会回显。模型切换会立即作用于后续请求。
        </p>
      </div>

      <Section title="数据与路径">
        <Row k="KNOWLEDGE_HOME" v={s.knowledge_home} />
        <Row k="数据目录" v={s.data_dir} />
        <Row k="外部资料目录" v={s.external_dir} />
        <Row k="Chroma 目录" v={s.chroma_persist_dir} />
        <Row k="Chroma 状态" v={s.chroma_ok ? "存在" : "不存在"} />
        <Row k="图谱目录" v={s.graph_persist_dir} />
      </Section>

      <Section title="模型">
        <Row k="Embedding 模型" v={s.embedding_model} />
        <Row k="Embedding 设备" v={s.embedding_device} />
        <Row k="LLM 模型" v={s.llm_model} />
        <Row k="LLM API" v={s.llm_api_base} />
        <Row k="LLM Key 已配置" v={s.llm_api_configured} />
        <Row k="评分/压缩 LLM" v={s.rerank_llm} />
        <Row k="本地 LLM 地址" v={s.local_llm_base} />
        <Row k="本地 LLM 模型" v={s.local_llm_model} />
      </Section>

      <section className="card settings-section llm-editor">
        <h3>切换模型 API</h3>
        <p className="muted settings-help">
          支持 DeepSeek、OpenAI 以及其他 OpenAI-compatible 服务。保存后会清理当前 Agent 缓存并热切换。
        </p>
        <div className="settings-form-grid">
          <label>供应商<select value={provider} onChange={(e) => chooseProvider(e.target.value)} disabled={saving}>
            {Object.entries(PROVIDERS).map(([value, item]) => <option key={value} value={value}>{item.label}</option>)}
            <option value="custom">自定义 OpenAI-compatible</option>
          </select></label>
          <label>模型<select value={model} onChange={(e) => setModel(e.target.value)} disabled={saving || loadingModels}>
            {models.map((item) => <option key={item} value={item}>{item}</option>)}
            {loadingModels ? <option value="">正在读取供应商模型…</option> : null}
            {!models.length && model ? <option value={model}>{model}</option> : null}
          </select></label>
          <label className="wide">Base URL<input value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} placeholder="https://api.example.com/v1" disabled={saving} /></label>
          <label className="wide">API Key（留空沿用当前密钥）<input type="password" value={apiKey} onChange={(e) => setApiKey(e.target.value)} placeholder={provider === "ollama" ? "本地 Ollama 通常无需填写" : (s.llm_api_configured ? "已配置，留空即可" : "粘贴供应商 API Key")} disabled={saving} autoComplete="new-password" /></label>
        </div>
        <div className="settings-actions">
          <button type="button" onClick={() => void refreshModels()} disabled={saving || loadingModels || !baseUrl}>
            {loadingModels ? "读取中…" : "从供应商读取模型"}
          </button>
          <button type="button" className="primary" onClick={() => void saveLlm()} disabled={saving || !model || !baseUrl}>
            {saving ? "切换中…" : "保存并热切换"}
          </button>
          {saved ? <span className="save-ok" role="status">已切换，后续对话使用新 API</span> : null}
          {modelError ? <span className="msg-error" role="alert">{modelError}</span> : null}
        </div>
      </section>

      <section className="card settings-section">
        <h3>Jev 工具选择</h3>
        <p className="muted settings-help">支持 TypeSafe 和 Vercel AI Gateway Key。保存后热加载；连接失败时 Agent 会使用规则选择器。</p>
        <div className="settings-form-grid"><label className="wide">Jev API Key<input type="password" value={jevKey} onChange={(e) => setJevKey(e.target.value)} placeholder={s.jev_api_configured ? "已配置，输入新 Key 可替换" : "粘贴 TypeSafe 或 Vercel Key"} disabled={saving} autoComplete="new-password" /></label></div>
        <div className="settings-actions">
          <button type="button" className="primary" disabled={saving || !jevKey} onClick={() => void setJevApiKey(jevKey).then((ok) => { if (ok) { setJevKey(""); setJevCheck(null); } })}>{saving ? "保存中…" : "保存并热加载"}</button>
          <button type="button" disabled={!s.jev_api_configured || checkingJev} onClick={() => void testJevConnection()}>{checkingJev ? "测试中…" : "测试连接"}</button>
          {s.jev_api_configured ? <span className="muted">密钥已配置，连接状态需测试</span> : <span className="muted">未配置，使用规则选择器</span>}
        </div>
        {jevCheck?.status === "ready" ? <p className="save-ok" role="status">Jev 连接可用（{jevCheck.provider === "vercel_gateway" ? "Vercel AI Gateway" : "TypeSafe"}）</p> : null}
        {jevCheck?.status === "rejected" ? <p className="msg-error" role="alert">Jev 提供商拒绝请求（HTTP {jevCheck.http_status}，{jevCheck.provider === "vercel_gateway" ? "Vercel AI Gateway" : "TypeSafe"}）；当前使用规则选择器。</p> : null}
        {jevCheck?.status === "unavailable" ? <p className="msg-error" role="alert">Jev 连接或响应异常；当前使用规则选择器。</p> : null}
        {jevCheckError ? <p className="msg-error" role="alert">{jevCheckError}</p> : null}
      </section>

      <Section title="模型来源">
        <Row k="HF Endpoint" v={s.hf_endpoint} />
        <Row k="HF 离线模式" v={s.hf_offline} />
      </Section>

      <Section
        title="检索与分块"
        footer={
          <div style={{ marginTop: 10 }}>
            {saving ? <p className="muted">保存中…</p> : null}
            {actionError ? (
              <p className="msg-error" role="alert">
                {actionError}
              </p>
            ) : null}
            <p className="muted" style={{ fontSize: 13 }}>
              图谱抽取模式：jieba 使用本地分词（快，零 API 调用）；LLM 使用
              DeepSeek 抽取（慢，但实体关系更准确）。切换立即生效，并写入{" "}
              <span className="mono">.env</span>。
            </p>
          </div>
        }
      >
        <Row k="混合检索（向量+BM25）" v={s.hybrid_search} />
        <Row k="文档评分" v={s.grading} />
        <Row k="查询改写" v={s.rewrite} />
        <Row k="上下文压缩" v={s.context_compression} />
        <Row k="知识图谱检索" v={s.graph_enabled} />
        <dt>图谱抽取模式</dt>
        <dd>
          <div className="mode-switch" aria-label="图谱抽取模式">
            <span className={s.graph_llm_extraction ? "muted" : "active"}>jieba</span>
            <button
              type="button"
              className="switch"
              role="switch"
              aria-checked={s.graph_llm_extraction}
              aria-label="切换图谱抽取模式"
              disabled={saving}
              onClick={() => void setGraphMode(!s.graph_llm_extraction)}
            >
              <span className="knob" />
            </button>
            <span className={s.graph_llm_extraction ? "active" : "muted"}>LLM</span>
          </div>
        </dd>
        <Row k="分块大小 / 重叠" v={`${s.chunk_size} / ${s.chunk_overlap}`} />
        <Row k="Top K" v={s.top_k} />
        <Row k="最大上下文 Token" v={s.max_context_tokens} />
      </Section>

      <section className="card settings-section">
        <h3>MCP</h3>
        <div className="mcp-master-row">
          <div>
            <div className="mcp-title">外部 MCP 工具</div>
            <div className="muted mcp-description">
              关闭后 Agent 不加载下方 Server；切换会立即丢弃 Agent 缓存，下次提问自动重建。
            </div>
          </div>
          <button
            type="button"
            className="switch"
            role="switch"
            aria-checked={s.mcp_enabled}
            aria-label="启用外部 MCP"
            disabled={saving}
            onClick={() => void setMcpEnabled(!s.mcp_enabled)}
          >
            <span className="knob" />
          </button>
        </div>
        <div className="mcp-runtime-status">
          <span className={`dot ${s.mcp_http_available ? "ready" : "error"}`} />
          HTTP MCP：{s.mcp_http_available ? "可用" : "不可用"}
          {s.mcp_http_error ? <span className="msg-error">{s.mcp_http_error}</span> : null}
        </div>
        <div className="mcp-list" aria-label="MCP Server 列表">
          {s.mcp_servers.length ? s.mcp_servers.map((server) => (
            <div className="mcp-server-row" key={server.name}>
              <div className="mcp-server-main">
                <div className="mcp-title">
                  {server.name}
                  <span className="mcp-kind">{server.type}</span>
                </div>
                <div className="muted mono mcp-target">{server.target || "未配置目标"}</div>
              </div>
              <button
                type="button"
                className="switch"
                role="switch"
                aria-checked={server.enabled}
                aria-label={`${server.enabled ? "停用" : "启用"} ${server.name}`}
                disabled={saving || !s.mcp_enabled}
                onClick={() => void setMcpServerEnabled(server.name, !server.enabled)}
              >
                <span className="knob" />
              </button>
            </div>
          )) : <p className="muted">尚未配置 MCP Server。</p>}
        </div>
        <p className="muted mcp-config-path">配置文件：<span className="mono">{s.mcp_config_path}</span></p>
        {actionError ? <p className="msg-error" role="alert">{actionError}</p> : null}
      </section>

      <Section
        title="安全"
        footer={
          onOpenTokenDialog && s.lan_protection ? (
            <button
              type="button"
              className="link-btn"
              onClick={onOpenTokenDialog}
              style={{ marginTop: 10 }}
            >
              输入访问令牌
            </button>
          ) : null
        }
      >
        <Row k="局域网访问保护" v={s.lan_protection} />
      </Section>
    </div>
  );
}
