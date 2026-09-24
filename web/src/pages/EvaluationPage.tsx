import { useCallback, useEffect, useState } from "react";

import { getLatestRetrievalEvaluation, getLatestToolSelectionEvaluation } from "../api/client";
import type { RetrievalEvaluationLatestResponse, ToolSelectionEvaluationLatestResponse, ToolSelectionEvaluationResult } from "../types/api";

export function EvaluationPage() {
  const [data, setData] = useState<RetrievalEvaluationLatestResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [toolData, setToolData] = useState<ToolSelectionEvaluationLatestResponse | null>(null);
  const [toolLoading, setToolLoading] = useState(true);
  const [toolError, setToolError] = useState<string | null>(null);

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

  const refreshTools = useCallback(async () => {
    setToolLoading(true);
    setToolError(null);
    try {
      setToolData(await getLatestToolSelectionEvaluation());
    } catch (reason) {
      setToolData(null);
      setToolError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setToolLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
    void refreshTools();
  }, [refresh, refreshTools]);

  const report = data?.status === "completed" ? data.report : null;
  const toolReport = toolData?.status === "completed" ? toolData.report : null;

  const renderToolMetrics = (title: string, result: ToolSelectionEvaluationResult) => (
    <div className="evaluation-tool-result">
      <h3>{title}</h3>
      <div className="evaluation-metrics" aria-label={`${title} 工具选择指标`}>
        <article className="evaluation-metric"><span>Top-1</span><strong>{(result.top1_accuracy * 100).toFixed(1)}%</strong><small>首选工具命中</small></article>
        <article className="evaluation-metric highlight"><span>Top-3</span><strong>{(result.top3_recall * 100).toFixed(1)}%</strong><small>前三候选包含目标工具</small></article>
        <article className="evaluation-metric"><span>写工具误暴露</span><strong>{(result.write_false_exposure_rate * 100).toFixed(1)}%</strong><small>{result.write_false_exposure_cases} 条只读用例出现写工具</small></article>
        <article className="evaluation-metric timing"><span>延迟 P50 / P95</span><strong>{result.latency_ms.p50.toFixed(3)} <i>/</i> {result.latency_ms.p95.toFixed(3)}<em>ms</em></strong><small>选择器耗时，不含模型/网络</small></article>
      </div>
      <div className="evaluation-cases">
        {result.cases.map((item) => (
          <article className="evaluation-case" key={item.case_id}>
            <span className={item.top1_hit ? "evaluation-case-status hit" : "evaluation-case-status miss"}>{item.first_expected_rank === null ? "MISS" : `#${item.first_expected_rank}`}</span>
            <div className="evaluation-case-main"><strong>{item.case_id}</strong><span>期望：{item.expected.join(", ")}</span><span>选择：{item.selected.slice(0, 3).join(", ") || "无"}</span>{item.false_write_exposure.length ? <span>误暴露写工具：{item.false_write_exposure.join(", ")}</span> : null}</div>
            <div className="evaluation-case-meta"><span>Top-3 {item.top3_hit ? "命中" : "未命中"}</span><span>{item.elapsed_ms.toFixed(3)} ms</span></div>
          </article>
        ))}
      </div>
    </div>
  );

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

      <section className="evaluation-tool-section" aria-labelledby="tool-evaluation-title">
        <div className="evaluation-section-head">
          <div><h2 id="tool-evaluation-title">工具选择评测</h2><p className="muted">合成查询与虚构工具目录；Jev 为本地确定性模拟，不代表真实 Jev 效果。</p></div>
          <button type="button" className="secondary" disabled={toolLoading} onClick={() => void refreshTools()}>{toolLoading ? "读取中…" : "刷新工具报告"}</button>
        </div>
        {toolLoading ? <div className="evaluation-state" role="status"><span className="retrieval-spinner" />正在读取工具评测报告…</div> : null}
        {toolError ? <div className="evaluation-state error" role="alert"><strong>工具评测报告读取失败</strong><span>{toolError}</span></div> : null}
        {!toolLoading && !toolError && toolData?.status === "empty" ? <div className="evaluation-state empty"><strong>还没有工具选择报告</strong><span>{toolData.message}</span><p>运行 <code>python -m evals.tools.run</code> 后刷新本页。</p></div> : null}
        {!toolLoading && !toolError && toolReport ? <>
          <div className="evaluation-banner"><span className="evaluation-banner-mark" aria-hidden="true">T</span><div><strong>离线合成基准 · 外部 Provider 未调用</strong><span>{toolReport.results.rule.total} 条用例 · DATASET v{toolReport.dataset_version} · {toolReport.dataset_sha256.slice(0, 12)}</span></div><time dateTime={toolReport.evaluated_at}>{new Date(toolReport.evaluated_at).toLocaleString()}</time></div>
          <div className="evaluation-tool-comparison">{renderToolMetrics("Rule baseline", toolReport.results.rule)}{renderToolMetrics("Jev adapter simulation", toolReport.results.jev_simulated)}</div>
          <p className="muted evaluation-limitation">{toolReport.limitations}</p>
        </> : null}
      </section>

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
