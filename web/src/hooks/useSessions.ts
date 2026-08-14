import { useCallback, useState } from "react";

import { deleteSession, listSessions } from "../api/client";
import type { SessionSummary } from "../types/api";

export interface UseSessionsResult {
  sessions: SessionSummary[];
  loading: boolean;
  error: string | null;
  reload: () => Promise<void>;
  remove: (id: string) => Promise<void>;
}

export function useSessions(): UseSessionsResult {
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setSessions(await listSessions());
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  const remove = useCallback(async (id: string) => {
    await deleteSession(id);
    setSessions((prev) => prev.filter((s) => s.id !== id));
  }, []);

  return { sessions, loading, error, reload, remove };
}
