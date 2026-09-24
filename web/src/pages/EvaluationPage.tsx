import { useCallback, useEffect, useState } from "react";

import { getLatestRetrievalEvaluation } from "../api/client";
import type { RetrievalEvaluationLatestResponse } from "../types/api";

export function EvaluationPage() {
  const [data, setData] = useState<RetrievalEvaluationLatestResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await getLatestRetrievalEvaluation());
    } catch (reason) {
      setData(null);
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const report = data?.status === "completed" ? data.report : null;

  return (
    <section className="page evaluation-page" aria-labelledby="evaluation-title">
      <div className="evaluation-heading">
        <div>
          <p className="evaluation-eyebrow">QUALITY / OFFLINE BENCHMARK</p>
          <h1 id="evaluation-title">检索评测</h1>
          <p className="muted">基于仓库冻结示例语料，隔离测量检索排名；不读取当前知识库，不调用在线 LLM。</p>
        </div>
        <button type="button" className="secondary evaluation-refresh" disabled={loading} onClick={() => void refresh()}>
          {loading ? "读取中…" : "刷新报告"}
        </button>
      </div>

      {loading ? (
        <div className="evaluation-state" role="status" aria-live="polite">
          <span className="retrieval-spinner" />正在读取最近的评测报告…
        </div>
      ) : null}

      {error ? (
        <div className="evaluation-state error" role="alert">
          <strong>报告读取失败</strong><span>{error}</span>
          <button type="button" className="secondary" disabled={loading} onClick={() => void refresh()}>重试</button>
        </div>
      ) : null}

      {!loading && !error && data?.status === "empty" ? (
        <div className="evaluation-state empty">
          <strong>还没有评测报告</strong>
          <span>{data.message}</span>
          <p>在项目目录运行 <code>python -m evals.retrieval.run</code>，完成后刷新本页。</p>
        </div>
      ) : null}

      {!loading && !error && report ? (
        <>
          <div className="evaluation-banner">
            <span className="evaluation-banner-mark" aria-hidden="true">R</span>
            <div>
              <strong>隔离示例基准 · 不是实际知识库质量报告</strong>
              <span>{report.metrics.total} 条用例 · {report.corpus.length} 份固定语料 · {report.embedding_model}</span>
            </div>
            <time dateTime={report.evaluated_at}>{new Date(report.evaluated_at).toLocaleString()}</time>
          </div>

          <div className="evaluation-metrics" aria-label="检索质量指标">
            {[1, 3, 5].map((k) => (
              <article className="evaluation-metric" key={k}>
                <span>Recall@{k}</span>
                <strong>{(report.metrics.recall_at_k[String(k)] ?? 0).toFixed(3)}</strong>
                <small>相关片段命中比例</small>
              </article>
            ))}
            <article className="evaluation-metric highlight">
              <span>MRR</span>
              <strong>{report.metrics.mrr.toFixed(3)}</strong>
              <small>首个相关片段的倒数名次</small>
            </article>
            <article className="evaluation-metric timing">
              <span>检索延迟 P50 / P95</span>
              <strong>{report.metrics.latency_ms.p50.toFixed(1)} <i>/</i> {report.metrics.latency_ms.p95.toFixed(1)}<em>ms</em></strong>
              <small>每次搜索耗时；不含模型和索引冷启动</small>
            </article>
          </div>

          <div className="evaluation-section-head">
            <div><h2>逐条结果</h2><p className="muted">按固定 case ID 展示命中证据，不保存查询文本或片段内容。</p></div>
            <span className="mono">DATASET v{report.dataset_version} · {report.dataset_sha256.slice(0, 12)}</span>
          </div>
          <div className="evaluation-cases">
            {report.metrics.cases.map((item) => (
              <article className="evaluation-case" key={item.case_id}>
                <span className={item.first_relevant_rank === null ? "evaluation-case-status miss" : "evaluation-case-status hit"}>
                  {item.first_relevant_rank === null ? "MISS" : `#${item.first_relevant_rank}`}
                </span>
                <div className="evaluation-case-main">
                  <strong>{item.case_id}</strong>
                  <span>期望：{item.relevant_ids.join(", ") || "—"}</span>
                  <span>命中：{item.retrieved_relevant_ids.join(", ") || "无"}</span>
                </div>
                <div className="evaluation-case-meta">
                  <span>R@5 {item.hits_at_k["5"] ?? 0}</span>
                  <span>{item.elapsed_ms.toFixed(1)} ms</span>
                </div>
              </article>
            ))}
          </div>

          <details className="evaluation-provenance">
            <summary>语料与运行配置</summary>
            <div className="evaluation-provenance-body">
              <p>分块 {report.chunking.size}/{report.chunking.overlap} · profile <code>{report.retrieval_profile}</code></p>
              {report.corpus.map((source) => <div key={source.source}><span>{source.source}</span><code>{source.sha256}</code></div>)}
            </div>
          </details>
        </>
      ) : null}
    </section>
  );
}
