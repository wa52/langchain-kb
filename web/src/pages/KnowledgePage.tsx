import { useEffect, useRef, useState } from "react";
import type { DragEvent, FormEvent } from "react";

import { useKnowledge } from "../hooks/useKnowledge";
import { useSync } from "../hooks/useSync";

const STATE_LABEL: Record<string, string> = {
  pending: "等待中",
  running: "处理中",
  done: "完成",
  failed: "失败",
};

function fmtTime(iso: string | null): string {
  if (!iso) return "从未";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString();
}

export function KnowledgePage() {
  const {
    stats,
    statsError,
    statsLoading,
    files,
    filesError,
    tasks,
    indexing,
    actionError,
    startPath,
    startUpload,
    removeFile,
    reindexFile,
  } = useKnowledge();
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [pathInput, setPathInput] = useState("");
  const [dragDepth, setDragDepth] = useState(0);
  const closeRef = useRef<HTMLButtonElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const [syncDirInput, setSyncDirInput] = useState("");
  const [fileFilter, setFileFilter] = useState("");
  const sync = useSync();

  useEffect(() => {
    if (!drawerOpen) return;
    closeRef.current?.focus();
    function onKey(e: KeyboardEvent): void {
      if (e.key === "Escape") setDrawerOpen(false);
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [drawerOpen]);

  useEffect(() => {
    if (!drawerOpen) return;
    function preventDefault(e: globalThis.DragEvent): void {
      e.preventDefault();
    }
    document.addEventListener("dragover", preventDefault);
    document.addEventListener("drop", preventDefault);
    return () => {
      document.removeEventListener("dragover", preventDefault);
      document.removeEventListener("drop", preventDefault);
    };
  }, [drawerOpen]);

  const chunks = stats?.chunks ?? null;
  const bm25 = stats?.bm25_chunks ?? null;
  const bm25Synced = chunks !== null && bm25 !== null ? chunks === bm25 : null;
  const visibleFiles = files.filter((file) =>
    `${file.source_type} ${file.file_key}`.toLowerCase().includes(fileFilter.trim().toLowerCase()),
  );

  async function submitPath(e: FormEvent): Promise<void> {
    e.preventDefault();
    const p = pathInput.trim();
    if (!p || indexing) return;
    if (await startPath(p)) setPathInput("");
  }

  function onDrop(e: DragEvent): void {
    e.preventDefault();
    setDragDepth(0);
    const files = Array.from(e.dataTransfer.files ?? []);
    if (files.length && !indexing) void startUpload(files);
  }

  return (
    <div className="page">
      <div className="card">
        <h2>知识库概览</h2>
        {statsLoading && !stats ? <p className="muted overview-state">正在读取知识库统计…</p> : null}
        {!statsLoading && statsError && !stats ? (
          <p className="msg-error" role="alert">{statsError}</p>
        ) : null}
        <dl className={statsLoading && !stats ? "kv is-loading" : "kv"}>
          <dt>documents</dt>
          <dd>{stats ? stats.documents : statsLoading ? "…" : "—"}</dd>
          <dt>chunks</dt>
          <dd>{stats ? stats.chunks : statsLoading ? "…" : "—"}</dd>
          <dt>bm25</dt>
          <dd>
            {bm25 ?? (statsLoading ? "…" : "—")}{" "}
            <span className="muted">
              {bm25Synced === null ? "" : bm25Synced ? "（已同步）" : "（未同步）"}
            </span>
          </dd>
          <dt>graph</dt>
          <dd>
            {stats
              ? `${stats.graph.entities} 实体 / ${stats.graph.relations} 关系`
              : statsLoading ? "读取中" : "—"}
          </dd>
        </dl>
        {stats?.index_task ? (
          <p className="muted" style={{ fontSize: 13, marginTop: 10 }}>
            最近索引任务：{STATE_LABEL[stats.index_task.status] ?? stats.index_task.status}
            {stats.index_task.result?.chunks_added != null
              ? ` · ${stats.index_task.result.chunks_added} chunks`
              : ""}
            {stats.index_task.error ? ` · ${stats.index_task.error}` : ""}
          </p>
        ) : null}
        {statsError && stats ? (
          <p className="msg-error" role="alert" style={{ marginTop: 10 }}>
            {statsError}
          </p>
        ) : null}
      </div>

      <div className="card">
        <div className="section-heading">
          <div>
            <h3>已索引资料</h3>
            <p className="muted" style={{ fontSize: 13 }}>
              {files.length ? `${files.length} 个文件` : "查看和管理已进入知识库的文件"}
            </p>
          </div>
          <input
            className="file-filter"
            type="search"
            value={fileFilter}
            onChange={(e) => setFileFilter(e.target.value)}
            placeholder="搜索文件"
            aria-label="搜索已索引文件"
          />
        </div>
        {filesError ? <p className="msg-error" role="alert">{filesError}</p> : null}
        {!filesError && !files.length && !statsLoading ? (
          <p className="muted file-empty">还没有已索引文件，请先添加资料。</p>
        ) : null}
        {visibleFiles.length ? (
          <ul className="tracked-file-list">
            {visibleFiles.map((file) => (
              <li key={`${file.source_type}:${file.file_key}`}>
                <div className="tracked-file-info">
                  <strong>{file.file_key}</strong>
                  <span className="muted">{file.source_type}</span>
                </div>
                <div className="tracked-file-actions">
                  <button
                    type="button"
                    className="link-btn"
                    disabled={indexing}
                    onClick={() => void reindexFile(file.file_key)}
                  >
                    重新索引
                  </button>
                  <button
                    type="button"
                    className="link-btn danger-link"
                    disabled={indexing}
                    onClick={() => {
                      if (window.confirm(`确定从知识库移除“${file.file_key}”？`)) {
                        void removeFile(file.file_key);
                      }
                    }}
                  >
                    移除
                  </button>
                </div>
              </li>
            ))}
          </ul>
        ) : fileFilter && !filesError ? (
          <p className="muted file-empty">没有匹配的文件。</p>
        ) : null}
      </div>

      <div className="card">
        <button type="button" className="primary" onClick={() => setDrawerOpen(true)}>
          添加资料
        </button>
        <p className="muted" style={{ marginTop: 10, fontSize: 13 }}>
          支持索引服务器本机上的文件/目录路径，或从浏览器拖拽上传文件。
        </p>
      </div>

      <div className="card">
        <h3>定时同步目录</h3>
        <p className="muted" style={{ fontSize: 13 }}>
          把服务器本机目录加入列表后，服务会每 {sync.status?.interval_hours ?? "—"}{" "}
          小时自动增量同步其中新增/变更的文档（原位读取，不复制）。适合把项目经验库等外部资料持续接入。
        </p>
        {sync.status?.dirs.length ? (
          <ul className="sync-dir-list">
            {sync.status.dirs.map((d) => (
              <li key={d}>
                <span className="mono">{d}</span>
                <button
                  type="button"
                  className="link-btn"
                  disabled={sync.status?.running}
                  onClick={() => void sync.removeDir(d)}
                >
                  移除
                </button>
              </li>
            ))}
          </ul>
        ) : (
          <p className="muted">尚未配置定时同步目录。</p>
        )}
        <form
          className="field-row"
          onSubmit={(e) => {
            e.preventDefault();
            const p = syncDirInput.trim();
            if (!p) return;
            void (async () => {
              if (await sync.addDir(p)) setSyncDirInput("");
            })();
          }}
        >
          <input
            type="text"
            value={syncDirInput}
            onChange={(e) => setSyncDirInput(e.target.value)}
            placeholder="服务器本机目录路径"
            aria-label="定时同步目录路径"
          />
          <button type="submit" className="secondary" disabled={!syncDirInput.trim()}>
            添加
          </button>
        </form>
        <div className="sync-meta" style={{ marginTop: 8 }}>
          <span className="muted">
            {sync.status?.running ? "同步中…" : "上次同步：" + fmtTime(sync.status?.last_sync_at ?? null)}
          </span>
          {sync.status?.last_result ? (
            <span className="muted">
              结果：{sync.status.last_result.changed} 变更 / {sync.status.last_result.chunks} 片段
            </span>
          ) : null}
          <button
            type="button"
            className="secondary"
            disabled={sync.status?.running || !sync.status?.enabled}
            onClick={() => void sync.triggerRun()}
          >
            立即同步
          </button>
        </div>
        {sync.actionError ? (
          <p className="msg-error" role="alert" style={{ marginTop: 8 }}>
            {sync.actionError}
          </p>
        ) : null}
      </div>

      {drawerOpen ? (
        <div className="drawer-backdrop" onClick={() => setDrawerOpen(false)}>
          <div
            className="drawer"
            role="dialog"
            aria-modal="true"
            aria-label="添加资料"
            onClick={(e) => e.stopPropagation()}
          >
            <button
              type="button"
              ref={closeRef}
              className="drawer-close"
              onClick={() => setDrawerOpen(false)}
              aria-label="关闭添加资料"
            >
              ✕
            </button>
            <h3 className="drawer-title">添加资料</h3>

            <form className="field-row" onSubmit={(e) => void submitPath(e)}>
              <input
                type="text"
                value={pathInput}
                onChange={(e) => setPathInput(e.target.value)}
                placeholder="服务器本机路径（文件或目录）"
                aria-label="本地路径"
                disabled={indexing}
              />
              <button type="submit" className="primary" disabled={indexing || !pathInput.trim()}>
                开始索引
              </button>
            </form>

            <div
              className={`drop-zone${dragDepth > 0 ? " drag" : ""}${indexing ? " busy" : ""}`}
              onDragEnter={(e) => {
                e.preventDefault();
                setDragDepth((d) => d + 1);
              }}
              onDragOver={(e) => e.preventDefault()}
              onDragLeave={() => setDragDepth((d) => Math.max(0, d - 1))}
              onDrop={onDrop}
            >
              <p>拖拽文件到此处上传</p>
              <button
                type="button"
                className="secondary"
                disabled={indexing}
                onClick={() => fileRef.current?.click()}
              >
                选择文件
              </button>
              <input
                ref={fileRef}
                type="file"
                multiple
                hidden
                aria-hidden="true"
                tabIndex={-1}
                onChange={(e) => {
                  const files = Array.from(e.target.files ?? []);
                  if (files.length && !indexing) void startUpload(files);
                  e.target.value = "";
                }}
              />
            </div>

            <p className="muted" style={{ fontSize: 13 }}>
              本地路径读取的是运行服务的那台电脑上的路径；拖拽上传会保存到该电脑的数据目录。
            </p>

            {actionError ? (
              <p className="msg-error" role="alert">
                {actionError}
              </p>
            ) : null}

            {indexing || tasks.length > 0 ? (
              <div className="task-list" aria-live="polite">
                {tasks.map((t) => (
                  <div key={t.task_id} className="task-item">
                    <span className={`task-state ${t.status}`}>
                      {STATE_LABEL[t.status] ?? t.status}
                    </span>
                    <span className="muted">
                      {t.status === "done"
                        ? `已索引 ${t.result?.chunks_added ?? 0} chunks`
                        : t.status === "failed"
                          ? t.error ?? "索引失败"
                          : t.progress ?? "处理中…"}
                    </span>
                  </div>
                ))}
              </div>
            ) : null}
          </div>
        </div>
      ) : null}
    </div>
  );
}
