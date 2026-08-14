import { useEffect, useState } from "react";

import { getSettings } from "../api/client";
import type { AppSettings } from "../types/api";

export interface UseSettingsResult {
  settings: AppSettings | null;
  error: string | null;
}

export function useSettings(): UseSettingsResult {
  const [settings, setSettings] = useState<AppSettings | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getSettings()
      .then((s) => {
        if (!cancelled) setSettings(s);
      })
      .catch((e) => {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : String(e));
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return { settings, error };
}
