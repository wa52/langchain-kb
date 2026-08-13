import { useEffect, useRef, useState } from "react";

import type { SystemStatus } from "../types/api";

export function KnowledgePage({ status }: { status: SystemStatus | null }) {
  const [drawerOpen, setDrawerOpen] = useState(false);
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!drawerOpen) return;
    closeRef.current?.focus();
    function onKey(e: KeyboardEvent): void {
      if (e.key === "Escape") setDrawerOpen(false);
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [drawerOpen]);

  const vectorCount = status?.vector_count ?? null;
  const bm25 = status?.bm25_chunks ?? null;
  const entityCount = status?.entity_count ?? null;

  const bm25Synced =
    vectorCount !== null && bm25 !== null ? vectorCount === bm25 : null;

  return (
    <div className="page">
      <div className="card">
        <h2>知识库概览</h2>
        <dl className="kv">
          <dt>chunks</dt>
          <dd>{vectorCount ?? "—"}</dd>
          <dt>bm25</dt>
          <dd>
            {bm25 ?? "—"}{" "}
            <span className="muted">
              {bm25Synced === null
                ? ""
                : bm25Synced
                  ? "（已同步）"
                  : "（未同步）"}
            </span>
          </dd>
          <dt>graph entities</dt>
          <dd>{entityCount ?? "—"}</dd>
        </dl>
      </div>

      <div className="card">
        <button type="button" className="primary" onClick={() => setDrawerOpen(true)}>
          添加资料
        </button>
        <p className="muted" style={{ marginTop: 10, fontSize: 13 }}>
          第一阶段：支持本地文件/目录路径索引；拖拽上传将在后续版本提供。
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
            <p className="muted" style={{ fontSize: 14 }}>
              当前阶段请使用命令行添加资料：
            </p>
            <pre className="mono" style={{ fontSize: 13, background: "var(--bg)", padding: 10, borderRadius: 8 }}>
              knowledge index &lt;路径&gt;
            </pre>
            <p className="muted" style={{ fontSize: 13 }}>
              本地路径读取的是运行服务的那台电脑上的路径；拖拽上传会保存到该电脑的数据目录（后续版本提供）。
            </p>
          </div>
        </div>
      ) : null}
    </div>
  );
}
