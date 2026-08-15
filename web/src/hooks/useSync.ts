import { useCallback, useEffect, useRef, useState } from "react";

import { addSyncDir, getSyncStatus, removeSyncDir, runSync } from "../api/client";
import type { SyncStatus } from "../api/client";

export interface UseSyncResult {
  status: SyncStatus | null;
  error: string | null;
  actionError: string | null;
  refresh: () => void;
  addDir: (path: string) => Promise<boolean>;
  removeDir: (path: string) => Promise<boolean>;
  triggerRun: () => Promise<boolean>;
}

export function useSync(): UseSyncResult {
  const [status, setStatus] = useState<SyncStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const pollRef = useRef<number | null>(null);

  const refresh = useCallback(() => {
    getSyncStatus()
      .then((s) => {
        setStatus(s);
        setError(null);
      })
      .catch((e) => {
        setError(e instanceof Error ? e.message : String(e));
      });
  }, []);

  useEffect(() => {
    refresh();
    return () => {
      if (pollRef.current) window.clearInterval(pollRef.current);
    };
  }, [refresh]);

  useEffect(() => {
    if (status?.running) {
      if (pollRef.current) window.clearInterval(pollRef.current);
      pollRef.current = window.setInterval(refresh, 3000);
    } else if (pollRef.current) {
      window.clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, [status?.running, refresh]);

  const addDir = useCallback(
    async (path: string): Promise<boolean> => {
      setActionError(null);
      try {
        await addSyncDir(path);
        refresh();
        return true;
      } catch (e) {
        setActionError(e instanceof Error ? e.message : String(e));
        return false;
      }
    },
    [refresh],
  );

  const removeDir = useCallback(
    async (path: string): Promise<boolean> => {
      setActionError(null);
      try {
        await removeSyncDir(path);
        refresh();
        return true;
      } catch (e) {
        setActionError(e instanceof Error ? e.message : String(e));
        return false;
      }
    },
    [refresh],
  );

  const triggerRun = useCallback(async (): Promise<boolean> => {
    setActionError(null);
    try {
      await runSync();
      refresh();
      return true;
    } catch (e) {
      setActionError(e instanceof Error ? e.message : String(e));
      return false;
    }
  }, [refresh]);

  return { status, error, actionError, refresh, addDir, removeDir, triggerRun };
}
