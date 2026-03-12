"use client";

import { useEffect, useState } from "react";
import { useApiKey, apiKeyHeader } from "@/lib/api-key";

const AGENT_API_URL =
  process.env.NEXT_PUBLIC_AGENT_API_URL || "http://localhost:8000";

export default function SettingsPage() {
  const { apiKey, setApiKey, clearApiKey } = useApiKey();
  const [inputValue, setInputValue] = useState("");
  const [status, setStatus] = useState<"idle" | "validating" | "valid" | "invalid" | "error">("idle");
  const [errorDetail, setErrorDetail] = useState("");

  // Show masked key on load
  useEffect(() => {
    if (apiKey) setInputValue(apiKey);
  }, [apiKey]);

  function maskedKey(key: string): string {
    if (key.length <= 12) return key;
    return key.slice(0, 7) + "..." + key.slice(-4);
  }

  async function handleSave() {
    const key = inputValue.trim();
    if (!key) return;

    setStatus("validating");
    setErrorDetail("");

    try {
      const res = await fetch(`${AGENT_API_URL}/api/settings/validate-key`, {
        method: "POST",
        headers: { "X-Anthropic-API-Key": key },
      });
      const data = await res.json();

      if (data.valid) {
        setApiKey(key);
        setStatus("valid");
      } else {
        setStatus("invalid");
        setErrorDetail(data.error || "Invalid API key");
      }
    } catch {
      setStatus("error");
      setErrorDetail("Could not reach the server.");
    }
  }

  function handleClear() {
    clearApiKey();
    setInputValue("");
    setStatus("idle");
    setErrorDetail("");
  }

  return (
    <div className="mx-auto max-w-xl px-6 py-12">
      <h1 className="font-serif text-2xl font-normal tracking-tight text-text-primary">
        Settings
      </h1>
      <p className="mt-2 text-sm text-text-secondary">
        Manage your API key and preferences.
      </p>

      <div className="mt-8 rounded-lg border border-border-subtle bg-surface-raised p-6">
        <h2 className="font-serif text-lg font-medium text-text-primary">
          Anthropic API Key
        </h2>
        <p className="mt-1 text-sm text-text-secondary">
          Optionally provide your own key. If not set, the server&apos;s default key is used.
        </p>

        {/* Current key display */}
        {apiKey && status !== "validating" && (
          <div className="mt-4 flex items-center gap-2 rounded-md border border-border-subtle bg-surface-overlay px-3 py-2">
            <span className="font-mono text-sm text-text-secondary">
              {maskedKey(apiKey)}
            </span>
            <span className="ml-auto inline-flex items-center gap-1 text-xs text-status-green">
              <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" />
              </svg>
              Active
            </span>
          </div>
        )}

        {/* Input */}
        <div className="mt-4">
          <input
            type="password"
            value={inputValue}
            onChange={(e) => {
              setInputValue(e.target.value);
              if (status === "valid" || status === "invalid") setStatus("idle");
            }}
            placeholder="sk-ant-api03-..."
            className="h-10 w-full rounded-md border border-border-default bg-surface-overlay px-3 font-mono text-sm text-text-primary placeholder:text-text-tertiary focus:border-border-focus focus:outline-none focus:ring-1 focus:ring-border-focus"
          />
        </div>

        {/* Status messages */}
        {status === "valid" && (
          <p className="mt-2 text-sm text-status-green">Key validated and saved.</p>
        )}
        {status === "invalid" && (
          <p className="mt-2 text-sm text-status-red">{errorDetail}</p>
        )}
        {status === "error" && (
          <p className="mt-2 text-sm text-status-red">{errorDetail}</p>
        )}

        {/* Actions */}
        <div className="mt-4 flex items-center gap-3">
          <button
            onClick={handleSave}
            disabled={!inputValue.trim() || status === "validating"}
            className="rounded-md bg-accent-amber px-4 py-2 text-sm font-medium text-surface-primary transition-colors hover:bg-accent-amber/90 disabled:opacity-50"
          >
            {status === "validating" ? "Validating..." : "Save Key"}
          </button>
          {apiKey && (
            <button
              onClick={handleClear}
              className="rounded-md border border-border-default px-4 py-2 text-sm font-medium text-text-secondary transition-colors hover:bg-surface-overlay"
            >
              Clear Key
            </button>
          )}
        </div>

        {/* Privacy note */}
        <p className="mt-4 text-xs text-text-tertiary">
          Your key is stored in your browser only. It is never sent to our database.
        </p>
      </div>
    </div>
  );
}
