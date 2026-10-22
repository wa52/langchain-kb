import { useState } from "react";
import type { FormEvent } from "react";

interface ComposerProps {
  streaming: boolean;
  onSend: (query: string) => void;
  onStop: () => void;
}

export function Composer({ streaming, onSend, onStop }: ComposerProps) {
  const [text, setText] = useState("");

  function submit(e: FormEvent): void {
    e.preventDefault();
    if (streaming) {
      onStop();
      return;
    }
    const query = text.trim();
    if (!query) return;
    onSend(query);
    setText("");
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>): void {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (streaming) {
        onStop();
      } else if (text.trim()) {
        onSend(text.trim());
        setText("");
      }
    }
  }

  return (
    <form className="composer" onSubmit={submit}>
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder="输入问题或任务…"
        aria-label="问题"
        rows={2}
      />
      <button
        type="submit"
        className="primary ui-hint"
        data-hint={streaming ? "停止当前回答" : "发送问题；Shift+Enter 可换行"}
        aria-label={streaming ? "停止生成" : "发送问题"}
        disabled={!streaming && !text.trim()}
      >
        <span aria-hidden="true">{streaming ? "■" : "↗"}</span> {streaming ? "停止" : "发送"}
      </button>
    </form>
  );
}
