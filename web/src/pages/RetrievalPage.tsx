import { useState, type FormEvent } from "react";

import { debugRetrieval } from "../api/client";
import type { RetrievalDebugResult, RetrievalDebugResponse } from "../types/api";

function score(value: number): string {
  return value.toFixed(3);
}

function ScoreChannel({ label, value, rank, tone }: {
  label: string;
  value: number;
  rank: number | null;
  tone: "dense" | "bm25" | "fusion";
}) {
  const percent = Math.max(0, Math.min(100, value * 100));
  return (
    <div className={`retrieval-score ${tone}`}>
      <div className="retrieval-score-label">
        <span>{label}</span>
        <strong>{score(value)}</strong>
        <span className="retrieval-channel-rank">{rank ? `#${rank}` : "—"}</span>
      </div>
      <div className="retrieval-score-track" aria-label={`${label} ${score(value)}`}>
        <span style={{ width: `${percent}%` }} />
      </div>
    </div>
  );
}

function ResultCard({ result }: { result: RetrievalDebugResult }) {
  return (
    <article className="retrieval-result">
      <header className="retrieval-result-head">
        <span className="retrieval-final-rank">{String(result.rank).padStart(2, "0")}</span>
        <div className="retrieval-result-source">
          <strong title={result.source}>{result.source}</strong>
          <span className="mono">{result.chunk_id || "无 chunk_id"}</span>
        </div>
        <div className="retrieval-fusion-badge">
          <span>融合</span>
          <strong>{score(result.fusion_score)}</strong>
        </div>
      </header>
      <pre className="retrieval-excerpt">{result.content || "（该片段没有文本内容）"}</pre>
      <div className="retrieval-channels" aria-label="各检索通道分数">
        <ScoreChannel label="Dense" value={result.dense_score} rank={result.dense_rank} tone="dense" />
        <ScoreChannel label="BM25" value={result.bm25_score} rank={result.bm25_rank} tone="bm25" />
        <ScoreChannel label="融合" value={result.fusion_score} rank={result.rank} tone="fusion" />
      </div>
    </article>
  );
}

export function RetrievalPage() {
  const [query, setQuery] = useState("");
  const [topK, setTopK] = useState(5);
  const [result, setResult] = useState<RetrievalDebugResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submittedQuery, setSubmittedQuery] = useState("");

  async function runSearch(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    await search(query);
  }

  async function search(rawQuery: string): Promise<void> {
    const normalized = rawQuery.trim();
    if (!normalized || loading) return;
    setLoading(true);
    setError(null);
    setSubmittedQuery(normalized);
    try {
      setResult(await debugRetrieval(normalized, topK));
    } catch (reason) {
      setResult(null);
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="page retrieval-page" aria-labelledby="retrieval-title">
      <div className="retrieval-intro">
        <div>
          <p className="retrieval-eyebrow">检索台 / RETRIEVAL LAB</p>
          <h1 id="retrieval-title">检索调试</h1>
          <p className="muted">
            查看同一查询在 Dense 与 BM25 通道中的命中和融合排序。此处只检索，不生成回答。
          </p>
        </div>
        <div className="retrieval-mark" aria-hidden="true">
          <span />
          <span />
          <span />
          <span />
          <span />
        </div>
      </div>

      <form className="retrieval-query card" onSubmit={(event) => void runSearch(event)}>
        <label htmlFor="retrieval-query-input">查询内容</label>
        <div className="retrieval-query-controls">
          <textarea
            id="retrieval-query-input"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="例如：HALCON 的 lines_facet 如何提取线状结构？"
            rows={2}
            maxLength={2000}
            disabled={loading}
          />
          <label className="retrieval-topk">
            返回数量
            <select value={topK} onChange={(event) => setTopK(Number(event.target.value))} disabled={loading}>
              {[5, 10, 20, 50].map((value) => <option key={value} value={value}>Top {value}</option>)}
            </select>
          </label>
          <button type="submit" className="primary retrieval-submit" disabled={loading || !query.trim()}>
            {loading ? "检索中…" : "测试检索"}
          </button>
        </div>
        <div className="retrieval-query-foot">
          <span className="muted">最长 2000 字 · 直接使用当前检索索引</span>
          <span className="mono muted">{query.length}/2000</span>
        </div>
      </form>

      {loading ? (
        <div className="retrieval-state" role="status" aria-live="polite">
          <span className="retrieval-spinner" />正在运行混合检索…
        </div>
      ) : null}

      {error ? (
        <div className="retrieval-state error" role="alert">
          <strong>检索没有完成</strong>
          <span>{error}</span>
          <button type="button" className="secondary" disabled={loading} onClick={() => void search(submittedQuery || query)}>
            {loading ? "检索中…" : "重试"}
          </button>
        </div>
      ) : null}

      {!loading && !error && result && result.results.length === 0 ? (
        <div className="retrieval-state empty">
          <strong>没有找到相关片段</strong>
          <span>试试更具体的算子名、概念词或文档主题。</span>
        </div>
      ) : null}

      {!loading && !error && result && result.results.length > 0 ? (
        <div className="retrieval-output" aria-live="polite">
          <div className="retrieval-output-head">
            <div>
              <h2>候选片段</h2>
              <p className="muted">“{result.query}”</p>
            </div>
            <div className="retrieval-run-meta">
              <strong>{result.results.length}</strong><span>条结果</span>
              <i />
              <strong>{result.elapsed_ms.toFixed(1)} ms</strong><span>总耗时</span>
            </div>
          </div>
          <div className="retrieval-legend" aria-label="分数说明">
            <span><i className="dense-dot" />Dense 语义相似度</span>
            <span><i className="bm25-dot" />BM25 词项匹配</span>
            <span><i className="fusion-dot" />融合分数与最终排名</span>
          </div>
          <div className="retrieval-results">
            {result.results.map((item) => <ResultCard key={`${item.rank}-${item.chunk_id}-${item.source}`} result={item} />)}
          </div>
        </div>
      ) : null}

      {!loading && !error && !result ? (
        <div className="retrieval-state idle">
          <span className="retrieval-idle-axis" aria-hidden="true" />
          <strong>输入问题，检查它如何命中知识库</strong>
          <span>结果会列出片段来源、各通道分数及融合后的顺序。</span>
        </div>
      ) : null}
    </section>
  );
}
