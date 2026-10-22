import { useState } from "react";

import { useChat } from "../hooks/useChat";
import { Composer } from "../components/chat/Composer";
import { EmptyState } from "../components/chat/EmptyState";
import { MessageList } from "../components/chat/MessageList";
import { SessionDrawer } from "../components/chat/SessionDrawer";
import type { SessionSummary, SystemStatus } from "../types/api";

interface ChatPageProps {
  status: SystemStatus | null;
  statusError?: string | null;
  onNavigate: (view: "knowledge") => void;
}

export function ChatPage({ status, statusError, onNavigate }: ChatPageProps) {
  const { messages, streaming, error, send, stop, newChat, sessionId, loadSession } = useChat();
  const [historyOpen, setHistoryOpen] = useState(false);
  const [resumeError, setResumeError] = useState<string | null>(null);

  const agentState = status?.components.agent?.state ?? "loading";
  const vectorCount = status?.vector_count ?? 0;
  const knowledgeEmpty = status !== null && vectorCount === 0;
  const isEmpty = messages.length === 0;

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
        <div className="chat-heading">
          <span className="chat-eyebrow">WORKSPACE / CHAT</span>
          <h1>对话</h1>
          <div className="chat-meta"><span className={`chat-state-dot ${statusError && !status ? "error" : agentState}`} aria-hidden="true" />{statusError && !status ? "服务暂不可用" : `Agent ${agentState}`}{status ? ` · ${vectorCount.toLocaleString()} 个知识片段` : ""}</div>
        </div>
        <div className="chat-head-actions">
          <button type="button" className="chat-action ui-hint" data-hint="开始一个没有上下文的新会话" onClick={newChat} disabled={streaming || isEmpty} aria-label="新建会话"><span aria-hidden="true">＋</span><span>新建会话</span></button>
          <button type="button" className="chat-action ui-hint" data-hint="查看和恢复历史会话" onClick={() => setHistoryOpen(true)} aria-label="历史会话"><span aria-hidden="true">◷</span><span>历史会话</span></button>
        </div>
      </div>
      {statusError && !status ? <div className="chat-connect-error" role="status">连接不到知识库服务。请确认服务已启动后重试。</div> : null}
      {isEmpty ? (
        <EmptyState
          knowledgeEmpty={knowledgeEmpty}
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
