import { useCallback, useEffect, useRef, useState } from "react";

import { getKnowledgeStats, getTaskStatus, indexPath, uploadFiles } from "../api/client";
import type { KnowledgeStats, TaskStatus } from "../types/api";

export interface UseKnowledgeResult {
  stats: KnowledgeStats | null;
  statsError: string | null;
  tasks: TaskStatus[];
  indexing: boolean;
  actionError: string | null;
  startPath: (path: string) => Promise<boolean>;
  startUpload: (files: File[]) => Promise<boolean>;
}

export function useKnowledge(): UseKnowledgeResult {
  const [stats, setStats] = useState<KnowledgeStats | null>(null);
  const [statsError, setStatsError] = useState<string | null>(null);
  const [tasks, setTasks] = useState<TaskStatus[]>([]);
  const [indexing, setIndexing] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const pollTimer = useRef<number | null>(null);
  const cancelledRef = useRef(false);

  const reload = useCallback(async () => {
    try {
      setStats(await getKnowledgeStats());
      setStatsError(null);
    } catch (e) {
      setStatsError(e instanceof Error ? e.message : String(e));
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  const poll = useCallback(
    async (ids: string[]) => {
      const statuses = (await Promise.all(
        ids.map((id) =>
          getTaskStatus(id).catch(() => null),
        ),
      )).filter((t): t is TaskStatus => t !== null);
      if (cancelledRef.current) return;
      setTasks((prev) => {
        const byId = new Map(statuses.map((t) => [t.task_id, t]));
        const merged = new Map(prev.map((t) => [t.task_id, t]));
        for (const [id, t] of byId) merged.set(id, t);
        return Array.from(merged.values());
      });
      const active = statuses.some(
        (t) => t.status === "pending" || t.status === "running",
      );
      if (active) {
        if (pollTimer.current) window.clearTimeout(pollTimer.current);
        pollTimer.current = window.setTimeout(() => void poll(ids), 2000);
      } else {
        setIndexing(false);
        void reload();
      }
    },
    [reload],
  );

  const startPath = useCallback(
    async (path: string): Promise<boolean> => {
      setActionError(null);
      setIndexing(true);
      try {
        const task = await indexPath(path);
        void poll([task.task_id]);
        return true;
      } catch (e) {
        setActionError(e instanceof Error ? e.message : String(e));
        setIndexing(false);
        return false;
      }
    },
    [poll],
  );

  const startUpload = useCallback(
    async (files: File[]): Promise<boolean> => {
      if (!files.length) return false;
      setActionError(null);
      setIndexing(true);
      try {
        const res = await uploadFiles(files);
        void poll(res.tasks.map((t) => t.task_id));
        return true;
      } catch (e) {
        setActionError(e instanceof Error ? e.message : String(e));
        setIndexing(false);
        return false;
      }
    },
    [poll],
  );

  useEffect(
    () => () => {
      cancelledRef.current = true;
      if (pollTimer.current) window.clearTimeout(pollTimer.current);
    },
    [],
  );

  return { stats, statsError, tasks, indexing, actionError, startPath, startUpload };
}
