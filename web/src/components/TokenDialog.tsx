import { useEffect, useRef, useState } from "react";

import { setAccessToken } from "../api/client";

interface TokenDialogProps {
  onClose: () => void;
}

export function TokenDialog({ onClose }: TokenDialogProps) {
  const [token, setToken] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    inputRef.current?.focus();
    function onKey(e: KeyboardEvent): void {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  function save(): void {
    const value = token.trim();
    if (!value || submitting) return;
    setSubmitting(true);
    setAccessToken(value);
    window.location.reload();
  }

  return (
    <div className="drawer-backdrop" onClick={onClose}>
      <div
        className="dialog"
        role="dialog"
        aria-modal="true"
        aria-label="输入访问令牌"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 className="dialog-title">需要访问令牌</h3>
        <p className="muted" style={{ fontSize: 13 }}>
          该服务已启用局域网访问保护。请输入服务端配置的{" "}
          <span className="mono">LAN_TOKEN</span> 以继续。
        </p>
        <input
          ref={inputRef}
          type="password"
          value={token}
          onChange={(e) => setToken(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") save();
          }}
          placeholder="LAN_TOKEN"
          aria-label="访问令牌"
          autoComplete="off"
        />
        <div className="dialog-actions">
          <button type="button" className="link-btn" onClick={onClose}>
            取消
          </button>
          <button type="button" className="primary" onClick={save} disabled={!token.trim() || submitting}>
            保存
          </button>
        </div>
      </div>
    </div>
  );
}
