import { useCallback, useEffect, useRef, useState } from "react";

import { getAgentTrace, getSession, streamChat } from "../api/client";
import {
  recordRunEnd,
  recordRunError,
  recordRunSources,
  recordRunStart,
  recordRunTools,
  recordStreamEvent,
  recordAgentTrace,
  recordFastRagTrace,
} from "../lib/telemetry";
import type { ChatMessage, SessionSummary, SourceItem } from "../types/api";

let seq = 0;
const nextId = (): string => `m_${Date.now().toString(36)}_${seq++}`;

const CITATION_RE = /\[来源:\s*([^\]]+)\]/g;

function makeGreeting(): ChatMessage {
  return {
    id: nextId(),
    role: "assistant",
    content: "你好，我是你的 AI 助手。有什么可以帮你？我可以从知识库中检索资料来回答你的问题。",
    streaming: false,
    interrupted: false,
    sources: [],
  };
}

function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null;
}

function deriveSources(content: string): SourceItem[] {
  const seen = new Set<string>();
  const sources: SourceItem[] = [];
  CITATION_RE.lastIndex = 0;
  for (const m of content.matchAll(CITATION_RE)) {
    const name = m[1].trim();
    if (name && !seen.has(name)) {
      seen.add(name);
      sources.push({ source: name, chunk_id: "", excerpt: null });
    }
  }
  return sources;
}

export interface UseChatResult {
  messages: ChatMessage[];
  streaming: boolean;
  error: string | null;
  sessionId: string | null;
  send: (query: string) => void;
  stop: () => void;
  newChat: () => void;
  loadSession: (summary: SessionSummary) => Promise<void>;
}

export function useChat(): UseChatResult {
  const [messages, setMessages] = useState<ChatMessage[]>(() => [makeGreeting()]);
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const streamSessionRef = useRef<string | null>(null);
  const runSeqRef = useRef(0);

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
      abortRef.current?.abort();
      const abort = new AbortController();
      abortRef.current = abort;
      const runSeq = ++runSeqRef.current;
      const assistantId = nextId();
      setMessages((prev) => [
        ...prev,
        { id: nextId(), role: "user", content: query },
        { id: assistantId, role: "assistant", content: "", streaming: true },
      ]);
      setStreaming(true);
      setError(null);
      streamSessionRef.current = sessionId;
      recordRunStart();

      void (async () => {
        const isCurrentRun = () => runSeq === runSeqRef.current;
        try {
          await streamChat(
            { query, session_id: sessionId },
            {
              onStart: (sid) => {
                if (!isCurrentRun()) return;
                if (sid) streamSessionRef.current = sid;
              },
              onToken: (text) => {
                if (!isCurrentRun()) return;
                appendToken(assistantId, text);
              },
              onSources: (sources) => {
                if (!isCurrentRun()) return;
                setSources(assistantId, sources);
              },
              onTool: (tools) => {
                if (!isCurrentRun()) return;
                recordRunTools(tools);
              },
              onEnd: (sid, interrupted, runId, fastRag) => {
                if (!isCurrentRun()) return;
                streamSessionRef.current = sid;
                setSessionId(sid);
                finish(assistantId, interrupted);
                if (runId) {
                  void getAgentTrace(runId).then((trace) => {
                    if (trace && isCurrentRun()) recordAgentTrace(trace);
                  }).catch(() => undefined);
                }
                if (fastRag) recordFastRagTrace(fastRag);
              },
              onError: (message) => {
                if (!isCurrentRun()) return;
                setError(message);
                fail(assistantId, message);
              },
              onEvent: (type, payload) => {
                if (!isCurrentRun()) return;
                recordStreamEvent(type);
                if (type === "sources" && isRecord(payload) && Array.isArray(payload.sources)) {
                  recordRunSources(payload.sources as Array<{ hit_chain?: string[] }>);
                } else if (type === "message_end" && isRecord(payload)) {
                  recordRunEnd(
                    typeof payload.elapsed_ms === "number" ? payload.elapsed_ms : null,
                  );
                } else if (type === "error" && isRecord(payload)) {
                  recordRunError(String(payload.error ?? "unknown error"));
                }
              },
            },
            abort.signal,
          );
        } catch (err) {
          if (!isCurrentRun()) return;
          if (abort.signal.aborted) {
            if (streamSessionRef.current) setSessionId(streamSessionRef.current);
            finish(assistantId, true);
          } else {
            const message = err instanceof Error ? err.message : String(err);
            setError(message);
            fail(assistantId, message);
          }
        } finally {
          if (runSeq === runSeqRef.current) {
            abortRef.current = null;
            streamSessionRef.current = null;
          }
        }
      })();
    },
    [sessionId, streaming, appendToken, setSources, finish, fail],
  );

  const stop = useCallback(() => {
    // Only abort the request: the run's catch path reconciles the
    // server-allocated session id from streamSessionRef before cleanup.
    abortRef.current?.abort();
  }, []);

  const newChat = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    streamSessionRef.current = null;
    runSeqRef.current++;
    setMessages([makeGreeting()]);
    setSessionId(null);
    setError(null);
    setStreaming(false);
  }, []);

  const loadSession = useCallback(async (summary: SessionSummary) => {
    abortRef.current?.abort();
    abortRef.current = null;
    streamSessionRef.current = null;
    const runSeq = ++runSeqRef.current;
    setStreaming(false);
    let detail;
    try {
      detail = await getSession(summary.id);
    } catch (err) {
      if (runSeq !== runSeqRef.current) return;
      throw err;
    }
    if (runSeq !== runSeqRef.current) return;
    const msgs: ChatMessage[] = (detail.messages ?? [])
      .filter((m) => m.role === "user" || m.role === "assistant" || m.role === "human" || m.role === "ai")
      .map((m) => {
        const content = m.content ?? "";
        return {
          id: nextId(),
          role: m.role === "user" || m.role === "human" ? "user" : "assistant",
          content,
          interrupted: Boolean(m.interrupted),
          sources: deriveSources(content),
        };
      });
    setMessages(msgs);
    setSessionId(detail.id);
    setError(null);
    setStreaming(false);
  }, []);

  useEffect(
    () => () => {
      abortRef.current?.abort();
      runSeqRef.current++;
    },
    [],
  );

  return { messages, streaming, error, sessionId, send, stop, newChat, loadSession };
}
