import { useChat } from "../hooks/useChat";
import { Composer } from "../components/chat/Composer";
import { EmptyState } from "../components/chat/EmptyState";
import { MessageList } from "../components/chat/MessageList";
import type { SystemStatus } from "../types/api";

interface ChatPageProps {
  status: SystemStatus | null;
  onNavigate: (view: "knowledge") => void;
}

export function ChatPage({ status, onNavigate }: ChatPageProps) {
  const { messages, streaming, error, send, stop } = useChat();

  const agentState = status?.components.agent?.state ?? "loading";
  const vectorCount = status?.vector_count ?? 0;

  return (
    <div className="chat-page">
      <div className="chat-meta">
        Agent {agentState}
        {status ? ` · ${vectorCount} chunks` : ""}
      </div>
      {messages.length === 0 ? (
        <EmptyState
          knowledgeEmpty={status !== null && vectorCount === 0}
          onAddMaterials={() => onNavigate("knowledge")}
        />
      ) : (
        <MessageList messages={messages} />
      )}
      {error ? (
        <div className="chat-error" role="alert">
          {error}
        </div>
      ) : null}
      <Composer streaming={streaming} onSend={send} onStop={stop} />
    </div>
  );
}
