import { useCallback, useRef, useState } from "react";

import { streamChat } from "../api/client";
import type { ChatMessage, SourceItem } from "../types/api";

let seq = 0;
const nextId = (): string => `m_${Date.now().toString(36)}_${seq++}`;

export interface UseChatResult {
  messages: ChatMessage[];
  streaming: boolean;
  error: string | null;
  sessionId: string | null;
  send: (query: string) => void;
  stop: () => void;
  newChat: () => void;
}

export function useChat(): UseChatResult {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const appendToken = useCallback((id: string, text: string) => {
    setMessages((prev) =>
      prev.map((m) => (m.id === id ? { ...m, content: m.content + text } : m)),
    );
  }, []);

  const setSources = useCallback((id: string, sources: SourceItem[]) => {
    setMessages((prev) =>
      prev.map((m) => (m.id === id ? { ...m, sources } : m)),
    );
  }, []);

  const finish = useCallback((id: string, interrupted: boolean) => {
    setMessages((prev) =>
      prev.map((m) =>
        m.id === id ? { ...m, streaming: false, interrupted: m.interrupted || interrupted } : m,
      ),
    );
    setStreaming(false);
  }, []);

  const fail = useCallback((id: string, message: string) => {
    setMessages((prev) =>
      prev.map((m) => (m.id === id ? { ...m, streaming: false, error: message } : m)),
    );
    setStreaming(false);
  }, []);

  const send = useCallback(
    (rawQuery: string) => {
      const query = rawQuery.trim();
      if (!query || streaming) return;
      const abort = new AbortController();
      abortRef.current = abort;
      const assistantId = nextId();
      setMessages((prev) => [
        ...prev,
        { id: nextId(), role: "user", content: query },
        { id: assistantId, role: "assistant", content: "", streaming: true },
      ]);
      setStreaming(true);
      setError(null);

      void (async () => {
        try {
          await streamChat(
            { query, session_id: sessionId },
            {
              onToken: (text) => appendToken(assistantId, text),
              onSources: (sources) => setSources(assistantId, sources),
              onEnd: (sid, interrupted) => {
                setSessionId(sid);
                finish(assistantId, interrupted);
              },
              onError: (message) => {
                setError(message);
                fail(assistantId, message);
              },
            },
            abort.signal,
          );
        } catch (err) {
          if (abort.signal.aborted) {
            finish(assistantId, true);
          } else {
            const message = err instanceof Error ? err.message : String(err);
            setError(message);
            fail(assistantId, message);
          }
        } finally {
          abortRef.current = null;
        }
      })();
    },
    [sessionId, streaming, appendToken, setSources, finish, fail],
  );

  const stop = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  const newChat = useCallback(() => {
    abortRef.current?.abort();
    setMessages([]);
    setSessionId(null);
    setError(null);
    setStreaming(false);
  }, []);

  return { messages, streaming, error, sessionId, send, stop, newChat };
}
