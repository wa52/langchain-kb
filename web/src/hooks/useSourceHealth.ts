import { useCallback, useEffect, useRef, useState } from "react";

import { getSourceHealthAudit, startSourceHealthAudit } from "../api/client";
import type { SourceHealthAuditStatus } from "../types/api";

export function useSourceHealth() {
  const [task, setTask] = useState<SourceHealthAuditStatus | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pollTimer = useRef<number | null>(null);
  const cancelledRef = useRef(false);

  const poll = useCallback(async (taskId: string) => {
    try {
      const current = await getSourceHealthAudit(taskId);
      if (cancelledRef.current) return;
      setTask(current);
      if (current.status === "pending" || current.status === "running") {
        pollTimer.current = window.setTimeout(() => void poll(taskId), 1200);
      } else {
        setRunning(false);
      }
    } catch (cause) {
      if (cancelledRef.current) return;
      setError(cause instanceof Error ? cause.message : String(cause));
      setRunning(false);
    }
  }, []);

  const run = useCallback(async () => {
    setError(null);
    setTask(null);
    setRunning(true);
    try {
      const started = await startSourceHealthAudit();
      if (cancelledRef.current) return;
      setTask(started);
      void poll(started.task_id);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
      setRunning(false);
    }
  }, [poll]);

  useEffect(() => {
    cancelledRef.current = false;
    return () => {
      cancelledRef.current = true;
      if (pollTimer.current) window.clearTimeout(pollTimer.current);
    };
  }, []);

  return { task, running, error, run };
}
