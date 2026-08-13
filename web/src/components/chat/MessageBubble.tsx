import { useState } from "react";

import type { ChatMessage, SourceItem } from "../../types/api";
import { SourceChips } from "./SourceChips";
import { SourceDrawer } from "./SourceDrawer";

interface MessageBubbleProps {
  message: ChatMessage;
}

export function MessageBubble({ message }: MessageBubbleProps) {
  const [drawerSource, setDrawerSource] = useState<SourceItem | null>(null);

  if (message.role === "user") {
    return (
      <div className="msg user">
        <div className="msg-body">{message.content}</div>
      </div>
    );
  }

  const hasSources = Boolean(message.sources && message.sources.length > 0);

  return (
    <div className="msg assistant">
      <div className="msg-body">
        {message.content || (message.streaming ? "…" : "")}
      </div>
      {message.error ? (
        <div className="msg-error" role="alert">
          {message.error}
        </div>
      ) : null}
      {message.interrupted ? <div className="msg-note">已停止生成</div> : null}
      {hasSources ? (
        <SourceChips sources={message.sources ?? []} onOpen={setDrawerSource} />
      ) : null}
      {drawerSource ? (
        <SourceDrawer source={drawerSource} onClose={() => setDrawerSource(null)} />
      ) : null}
    </div>
  );
}
