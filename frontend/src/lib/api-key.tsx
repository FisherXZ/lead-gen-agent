"use client";

import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

const STORAGE_KEY = "anthropic-api-key";

interface ApiKeyContextValue {
  apiKey: string | null;
  setApiKey: (key: string) => void;
  clearApiKey: () => void;
}

const ApiKeyContext = createContext<ApiKeyContextValue>({
  apiKey: null,
  setApiKey: () => {},
  clearApiKey: () => {},
});

export function ApiKeyProvider({ children }: { children: ReactNode }) {
  const [apiKey, setApiKeyState] = useState<string | null>(null);

  // Hydrate from localStorage on mount
  useEffect(() => {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored) setApiKeyState(stored);
  }, []);

  function setApiKey(key: string) {
    localStorage.setItem(STORAGE_KEY, key);
    setApiKeyState(key);
  }

  function clearApiKey() {
    localStorage.removeItem(STORAGE_KEY);
    setApiKeyState(null);
  }

  return (
    <ApiKeyContext.Provider value={{ apiKey, setApiKey, clearApiKey }}>
      {children}
    </ApiKeyContext.Provider>
  );
}

export function useApiKey() {
  return useContext(ApiKeyContext);
}

/**
 * Returns a headers object with the user's API key if set.
 * Safe to call during SSR (returns empty object).
 */
export function apiKeyHeader(): Record<string, string> {
  if (typeof window === "undefined") return {};
  const key = localStorage.getItem(STORAGE_KEY);
  return key ? { "X-Anthropic-API-Key": key } : {};
}
