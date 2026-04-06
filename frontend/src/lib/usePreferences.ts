"use client";

import { useCallback, useEffect, useRef, useState } from "react";

type Preferences = Record<string, unknown>;

export function usePreferences() {
  const [preferences, setPreferences] = useState<Preferences>({});
  const [loading, setLoading] = useState(true);
  const prefsRef = useRef(preferences);

  useEffect(() => {
    prefsRef.current = preferences;
  }, [preferences]);

  useEffect(() => {
    fetch("/api/preferences")
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => {
        if (data?.preferences) setPreferences(data.preferences);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const updatePreferences = useCallback(
    async (updates: Preferences) => {
      const prev = prefsRef.current;
      setPreferences((p) => ({ ...p, ...updates }));

      const res = await fetch("/api/preferences", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(updates),
      });

      if (res.ok) {
        const data = await res.json();
        setPreferences(data.preferences);
      } else {
        setPreferences(prev);
      }
    },
    []
  );

  return { preferences, updatePreferences, loading };
}
