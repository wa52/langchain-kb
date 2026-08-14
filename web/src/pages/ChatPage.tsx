import { useState } from "react";

import { useChat } from "../hooks/useChat";
import { Composer } from "../components/chat/Composer";
import { EmptyState } from "../components/chat/EmptyState";
import { MessageList } from "../components/chat/MessageList";
import { SessionDrawer } from "../components/chat/SessionDrawer";
import type { SessionSummary, SystemStatus } from "../types/api";

interface ChatPageProps {
  status: SystemStatus | null;
  onNavigate: (view: "knowledge") => void;
}

export function ChatPage({ status, onNavigate }: ChatPageProps) {
  const { messages, streaming, error, send, stop, sessionId, loadSession } = useChat();
  const [historyOpen, setHistoryOpen] = useState(false);
  const [resumeError, setResumeError] = useState<string | null>(null);

  const agentState = status?.components.agent?.state ?? "loading";
  const vectorCount = status?.vector_count ?? 0;

  async function resume(s: SessionSummary): Promise<void> {
    try {
      await loadSession(s);
      setResumeError(null);
    } catch (e) {
      setResumeError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div className="chat-page">
      <div className="chat-head">
        <div className="chat-meta">
          Agent {agentState}
          {status ? ` · ${vectorCount} chunks` : ""}
        </div>
        <button
          type="button"
          className="link-btn"
          onClick={() => setHistoryOpen(true)}
        >
          历史会话
        </button>
      </div>
      {messages.length === 0 ? (
        <EmptyState
          knowledgeEmpty={status !== null && vectorCount === 0}
          onAddMaterials={() => onNavigate("knowledge")}
        />
      ) : (
        <MessageList messages={messages} />
      )}
      {error || resumeError ? (
        <div className="chat-error" role="alert">
          {error ?? resumeError}
        </div>
      ) : null}
      <Composer streaming={streaming} onSend={send} onStop={stop} />
      {historyOpen ? (
        <SessionDrawer
          currentSessionId={sessionId}
          onClose={() => setHistoryOpen(false)}
          onResume={resume}
        />
      ) : null}
    </div>
  );
}
