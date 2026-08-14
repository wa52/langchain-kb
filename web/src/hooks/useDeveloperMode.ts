import { useCallback, useState } from "react";

const KEY = "dev_mode_enabled";

export function useDeveloperMode(): [boolean, () => void] {
  const [enabled, setEnabled] = useState<boolean>(() => {
    try {
      return localStorage.getItem(KEY) === "1";
    } catch {
      return false;
    }
  });

  const toggle = useCallback(() => {
    setEnabled((prev) => {
      const next = !prev;
      try {
        localStorage.setItem(KEY, next ? "1" : "0");
      } catch {
        /* storage unavailable */
      }
      return next;
    });
  }, []);

  return [enabled, toggle];
}
