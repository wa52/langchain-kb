import { useEffect, useRef, useState } from "react";
import type { DragEvent, FormEvent } from "react";

import { useKnowledge } from "../hooks/useKnowledge";

const STATE_LABEL: Record<string, string> = {
  pending: "等待中",
  running: "处理中",
  done: "完成",
  failed: "失败",
};

export function KnowledgePage() {
  const {
    stats,
    statsError,
    tasks,
    indexing,
    actionError,
    startPath,
    startUpload,
  } = useKnowledge();
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [pathInput, setPathInput] = useState("");
  const [dragDepth, setDragDepth] = useState(0);
  const closeRef = useRef<HTMLButtonElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);

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
        <dl className="kv">
          <dt>documents</dt>
          <dd>{stats?.documents ?? "—"}</dd>
          <dt>chunks</dt>
          <dd>{stats?.chunks ?? "—"}</dd>
          <dt>bm25</dt>
          <dd>
            {bm25 ?? "—"}{" "}
            <span className="muted">
              {bm25Synced === null ? "" : bm25Synced ? "（已同步）" : "（未同步）"}
            </span>
          </dd>
          <dt>graph</dt>
          <dd>
            {stats
              ? `${stats.graph.entities} 实体 / ${stats.graph.relations} 关系`
              : "—"}
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
        {statsError ? (
          <p className="msg-error" role="alert" style={{ marginTop: 10 }}>
            {statsError}
          </p>
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
