import { useEffect, useRef, useState } from "react";

import type { SourceItem } from "../../types/api";

interface SourceDrawerProps {
  source: SourceItem;
  onClose: () => void;
}

const CHAIN_LABEL: Record<string, string> = {
  vector: "向量检索",
  bm25: "BM25",
  graph: "知识图谱",
};

export function SourceDrawer({ source, onClose }: SourceDrawerProps) {
  const closeRef = useRef<HTMLButtonElement>(null);
  const [copyState, setCopyState] = useState<"idle" | "copied" | "failed">("idle");
  const timerRef = useRef<number | null>(null);

  useEffect(() => {
    closeRef.current?.focus();
    function onKey(e: KeyboardEvent): void {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      if (timerRef.current) window.clearTimeout(timerRef.current);
    };
  }, [onClose]);

  const reference = `[来源: ${source.source}]`;

  async function copyReference(): Promise<void> {
    try {
      await navigator.clipboard.writeText(reference);
      setCopyState("copied");
      timerRef.current = window.setTimeout(() => setCopyState("idle"), 1600);
    } catch {
      setCopyState("failed");
      timerRef.current = window.setTimeout(() => setCopyState("idle"), 1600);
    }
  }

  const chain = (source.hit_chain ?? []).map((c) => CHAIN_LABEL[c] ?? c);

  const copyLabel =
    copyState === "copied" ? "已复制" : copyState === "failed" ? "复制失败" : "复制引用";

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
          {chain.length > 0 ? (
            <>
              <dt>候选检索链路</dt>
              <dd>{chain.join(" · ")}</dd>
            </>
          ) : null}
          {source.chunk_id ? (
            <>
              <dt>chunk id</dt>
              <dd className="mono">{source.chunk_id}</dd>
            </>
          ) : null}
          {source.excerpt ? (
            <>
              <dt>摘录</dt>
              <dd className="drawer-excerpt">{source.excerpt}</dd>
            </>
          ) : null}
          <dt>引用</dt>
          <dd className="mono">{reference}</dd>
        </dl>
        <button
          type="button"
          className="link-btn"
          onClick={() => void copyReference()}
        >
          {copyLabel}
        </button>
      </div>
    </div>
  );
}
