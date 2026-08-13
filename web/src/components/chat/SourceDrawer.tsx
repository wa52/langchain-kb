import { useEffect, useRef } from "react";

import type { SourceItem } from "../../types/api";

interface SourceDrawerProps {
  source: SourceItem;
  onClose: () => void;
}

export function SourceDrawer({ source, onClose }: SourceDrawerProps) {
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    closeRef.current?.focus();
    function onKey(e: KeyboardEvent): void {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="drawer-backdrop" onClick={onClose}>
      <div
        className="drawer"
        role="dialog"
        aria-modal="true"
        aria-label="来源详情"
        onClick={(e) => e.stopPropagation()}
      >
        <button
          type="button"
          ref={closeRef}
          className="drawer-close"
          onClick={onClose}
          aria-label="关闭来源详情"
        >
          ✕
        </button>
        <h3 className="drawer-title">{source.source}</h3>
        <dl>
          <dt>chunk id</dt>
          <dd>{source.chunk_id || "—"}</dd>
          {source.excerpt ? (
            <>
              <dt>摘录</dt>
              <dd>{source.excerpt}</dd>
            </>
          ) : null}
        </dl>
        <p className="muted" style={{ fontSize: 13 }}>
          命中链路与引用文本会在后续版本提供。
        </p>
      </div>
    </div>
  );
}
