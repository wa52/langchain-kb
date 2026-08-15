import { useCallback, useEffect, useState } from "react";

import { getSettings, setGraphExtractionMode } from "../api/client";
import type { AppSettings } from "../types/api";

export interface UseSettingsResult {
  settings: AppSettings | null;
  error: string | null;
  actionError: string | null;
  saving: boolean;
  reload: () => void;
  setGraphMode: (enabled: boolean) => Promise<boolean>;
}

export function useSettings(): UseSettingsResult {
  const [settings, setSettings] = useState<AppSettings | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const reload = useCallback(() => {
    getSettings()
      .then((s) => {
        setSettings(s);
        setError(null);
      })
      .catch((e) => {
        setError(e instanceof Error ? e.message : String(e));
      });
  }, []);

  useEffect(() => {
    reload();
  }, [reload]);

  const setGraphMode = useCallback(
    async (enabled: boolean): Promise<boolean> => {
      setSaving(true);
      setActionError(null);
      try {
        const res = await setGraphExtractionMode(enabled);
        setSettings((prev) =>
          prev
            ? { ...prev, graph_llm_extraction: res.graph_llm_extraction }
            : prev,
        );
        return true;
      } catch (e) {
        setActionError(e instanceof Error ? e.message : String(e));
        return false;
      } finally {
        setSaving(false);
      }
    },
    [],
  );

  return { settings, error, actionError, saving, reload, setGraphMode };
}
