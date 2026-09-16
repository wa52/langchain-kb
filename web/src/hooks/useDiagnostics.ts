import { useCallback, useEffect, useRef, useState } from "react";

import { getDiagnostics, repairDiagnostics, startDiagnostics } from "../api/client";
import type { DiagnosticsTaskStatus } from "../types/api";

export interface UseDiagnosticsResult {
  task: DiagnosticsTaskStatus | null;
  running: boolean;
  error: string | null;
  run: () => Promise<void>;
  repair: (name: string) => Promise<boolean>;
}

export function useDiagnostics(): UseDiagnosticsResult {
  const [task, setTask] = useState<DiagnosticsTaskStatus | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pollTimer = useRef<number | null>(null);
  const cancelledRef = useRef(false);

  const poll = useCallback(async (id: string) => {
    let t: DiagnosticsTaskStatus;
    try {
      t = await getDiagnostics(id);
    } catch (e) {
      if (cancelledRef.current) return;
      setError(e instanceof Error ? e.message : String(e));
      setRunning(false);
      return;
    }
    if (cancelledRef.current) return;
    setTask(t);
    if (t.status === "pending" || t.status === "running") {
      if (pollTimer.current) window.clearTimeout(pollTimer.current);
      pollTimer.current = window.setTimeout(() => void poll(id), 2000);
    } else {
      setRunning(false);
    }
  }, []);

  const run = useCallback(async () => {
    setError(null);
    setRunning(true);
    setTask(null);
    try {
      const res = await startDiagnostics();
      void poll(res.task_id);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setRunning(false);
    }
  }, [poll]);

  const repair = useCallback(
    async (name: string): Promise<boolean> => {
      if (!task) return false;
      setError(null);
      try {
        const res = await repairDiagnostics(task.task_id, name);
        return res.repaired;
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
        return false;
      }
    },
    [task],
  );

  useEffect(() => {
    cancelledRef.current = false;
    return () => {
      cancelledRef.current = true;
      if (pollTimer.current) window.clearTimeout(pollTimer.current);
    };
  }, []);

  return { task, running, error, run, repair };
}
