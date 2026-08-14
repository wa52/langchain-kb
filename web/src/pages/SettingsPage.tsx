import type { ReactNode } from "react";

import { useSettings } from "../hooks/useSettings";
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

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="card settings-section">
      <h3>{title}</h3>
      <dl className="kv">{children}</dl>
    </section>
  );
}

export function SettingsPage() {
  const { settings, error } = useSettings();

  if (error) {
    return (
      <div className="page">
        <div className="card">
          <h2>设置（只读）</h2>
          <p className="chat-error" role="alert">
            配置读取失败：{error}
          </p>
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
        <h2>设置（只读）</h2>
        <p className="muted" style={{ fontSize: 13 }}>
          第一阶段不显示任何密钥，也不在界面中编辑配置。配置变更请编辑数据目录下的{" "}
          <span className="mono">.env</span> 后重启服务。
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

      <Section title="模型来源">
        <Row k="HF Endpoint" v={s.hf_endpoint} />
        <Row k="HF 离线模式" v={s.hf_offline} />
      </Section>

      <Section title="检索与分块">
        <Row k="混合检索（向量+BM25）" v={s.hybrid_search} />
        <Row k="文档评分" v={s.grading} />
        <Row k="查询改写" v={s.rewrite} />
        <Row k="上下文压缩" v={s.context_compression} />
        <Row k="知识图谱检索" v={s.graph_enabled} />
        <Row k="图谱 LLM 抽取" v={s.graph_llm_extraction} />
        <Row k="分块大小 / 重叠" v={`${s.chunk_size} / ${s.chunk_overlap}`} />
        <Row k="Top K" v={s.top_k} />
        <Row k="最大上下文 Token" v={s.max_context_tokens} />
      </Section>

      <Section title="扩展与安全">
        <Row k="MCP 配置" v={s.mcp_config_path} />
        <Row k="MCP 已启用" v={s.mcp_enabled} />
        <Row k="局域网访问保护" v={s.lan_protection} />
      </Section>
    </div>
  );
}
