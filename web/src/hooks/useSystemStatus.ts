import { useEffect, useState } from "react";

import type { SystemStatus } from "../types/api";

export interface UseSystemStatusResult {
  status: SystemStatus | null;
  error: string | null;
}

export function useSystemStatus(): UseSystemStatusResult {
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    async function load(): Promise<void> {
      try {
        const resp = await fetch("/api/v1/status", {
          headers: { Accept: "application/json" },
        });
        if (!resp.ok) throw new Error(`状态请求失败 (${resp.status})`);
        const data = (await resp.json()) as SystemStatus;
        if (active) {
          setStatus(data);
          setError(null);
        }
      } catch (e) {
        if (active) setError(e instanceof Error ? e.message : String(e));
      }
    }
    void load();
    const id = setInterval(load, 10000);
    return () => {
      active = false;
      clearInterval(id);
    };
  }, []);

  return { status, error };
}
