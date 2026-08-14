import { useEffect, useRef, useState } from "react";

import { useSessions } from "../../hooks/useSessions";
import type { SessionSummary } from "../../types/api";

interface SessionDrawerProps {
  currentSessionId: string | null;
  onClose: () => void;
  onResume: (summary: SessionSummary) => Promise<void>;
}

export function SessionDrawer({ currentSessionId, onClose, onResume }: SessionDrawerProps) {
  const { sessions, loading, error, reload, remove } = useSessions();
  const [confirmId, setConfirmId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    closeRef.current?.focus();
    function onKey(e: KeyboardEvent): void {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  useEffect(() => {
    void reload();
  }, [reload]);

  async function handleDelete(id: string): Promise<void> {
    if (confirmId !== id) {
      setConfirmId(id);
      return;
    }
    setActionError(null);
    try {
      await remove(id);
      setConfirmId(null);
    } catch (e) {
      setActionError(e instanceof Error ? e.message : String(e));
      setConfirmId(null);
    }
  }

  async function handleResume(s: SessionSummary): Promise<void> {
    setActionError(null);
    try {
      await onResume(s);
      onClose();
    } catch (e) {
      setActionError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div className="drawer-backdrop" onClick={onClose}>
      <div
        className="drawer"
        role="dialog"
        aria-modal="true"
        aria-label="历史会话"
        onClick={(e) => e.stopPropagation()}
      >
        <button
          type="button"
          ref={closeRef}
          className="drawer-close"
          onClick={onClose}
          aria-label="关闭历史会话"
        >
          ✕
        </button>
        <h3 className="drawer-title">历史会话</h3>
        {loading ? <p className="muted">加载中…</p> : null}
        {error ? (
          <p className="msg-error" role="alert">
            {error}
          </p>
        ) : null}
        {actionError ? (
          <p className="msg-error" role="alert">
            {actionError}
          </p>
        ) : null}
        <ul className="session-list">
          {sessions.map((s) => (
            <li key={s.id} className={s.id === currentSessionId ? "active" : ""}>
              <div className="session-row">
                <button
                  type="button"
                  className="session-load"
                  onClick={() => void handleResume(s)}
                  title={`继续会话：${s.title}`}
                >
                  <span className="session-title">{s.title}</span>
                  <span className="session-meta">
                    {s.created} · {s.turns} 轮
                  </span>
                </button>
                <button
                  type="button"
                  className="session-del"
                  onClick={() => void handleDelete(s.id)}
                  aria-label={`删除会话 ${s.title}`}
                >
                  {confirmId === s.id ? "确认删除?" : "删除"}
                </button>
              </div>
            </li>
          ))}
        </ul>
        {!loading && sessions.length === 0 ? (
          <p className="muted">暂无历史会话。</p>
        ) : null}
      </div>
    </div>
  );
}
