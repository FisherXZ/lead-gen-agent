"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

const AGENT_API_URL =
  process.env.NEXT_PUBLIC_AGENT_API_URL || "http://localhost:8000";

const ERROR_MESSAGES: Record<string, string> = {
  api_key_missing: "API key not configured. Contact your admin.",
  anthropic_error: "AI service error. Please try again in a few minutes.",
  search_tool_error: "Search tools are experiencing issues. Try again later.",
  max_iterations: "Research timed out. The agent couldn't complete in time.",
  no_report: "Agent ended without reporting findings. Try again.",
  db_error: "Database error. Please try again.",
  unknown: "An unexpected error occurred.",
};

function parseErrorMessage(status: number, body: string): string {
  try {
    const json = JSON.parse(body);
    // Check for error_category in the response detail
    const detail = json.detail || "";
    if (json.error_category) {
      return ERROR_MESSAGES[json.error_category] || detail;
    }
    // HTTP status-based fallbacks
    if (status === 401) return ERROR_MESSAGES.api_key_missing;
    if (status === 429) return "Rate limited. Please wait a moment and retry.";
    if (status === 503) return "Service unavailable. Check configuration.";
    if (detail) return typeof detail === "string" ? detail.slice(0, 120) : String(detail);
  } catch {
    // Not JSON
  }
  if (status === 401) return ERROR_MESSAGES.api_key_missing;
  if (status === 429) return "Rate limited. Please wait a moment and retry.";
  return `Request failed (${status})`;
}

export default function ResearchButton({
  projectId,
  hasExisting,
}: {
  projectId: string;
  hasExisting: boolean;
}) {
  const [status, setStatus] = useState<"idle" | "loading" | "done" | "error">(
    "idle"
  );
  const [errorMessage, setErrorMessage] = useState<string>("");
  const [warningMessage, setWarningMessage] = useState<string>("");
  const router = useRouter();

  async function handleResearch() {
    setStatus("loading");
    setErrorMessage("");
    setWarningMessage("");
    try {
      const res = await fetch(`${AGENT_API_URL}/api/discover`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ project_id: projectId }),
      });

      if (!res.ok) {
        const errText = await res.text();
        setErrorMessage(parseErrorMessage(res.status, errText));
        setStatus("error");
        return;
      }

      // Check for partial success (completed but with error)
      const data = await res.json();
      if (data.error_category) {
        setWarningMessage(
          ERROR_MESSAGES[data.error_category] || data.error_message || ""
        );
      }

      setStatus("done");
      // Refresh server data so the page shows the new discovery
      router.refresh();
    } catch (err) {
      console.error("Research failed:", err);
      setErrorMessage("Network error. Check your connection and try again.");
      setStatus("error");
    }
  }

  if (status === "loading") {
    return (
      <button
        disabled
        className="inline-flex items-center gap-2 rounded-md bg-slate-100 px-4 py-2 text-sm font-medium text-slate-400"
      >
        <svg
          className="h-4 w-4 animate-spin"
          viewBox="0 0 24 24"
          fill="none"
        >
          <circle
            className="opacity-25"
            cx="12"
            cy="12"
            r="10"
            stroke="currentColor"
            strokeWidth="4"
          />
          <path
            className="opacity-75"
            fill="currentColor"
            d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
          />
        </svg>
        Researching...
      </button>
    );
  }

  if (status === "done") {
    return (
      <div>
        <span className="inline-flex items-center gap-1.5 text-sm font-medium text-emerald-600">
          <svg
            className="h-4 w-4"
            fill="none"
            viewBox="0 0 24 24"
            strokeWidth={2}
            stroke="currentColor"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M4.5 12.75l6 6 9-13.5"
            />
          </svg>
          Research complete
        </span>
        {warningMessage && (
          <p className="mt-1 text-xs text-amber-600">{warningMessage}</p>
        )}
      </div>
    );
  }

  if (status === "error") {
    return (
      <div className="flex flex-col gap-1">
        <div className="flex items-center gap-3">
          <span className="text-sm text-red-500">
            {errorMessage || "Research failed"}
          </span>
          <button
            onClick={handleResearch}
            className="rounded-md border border-slate-200 px-3 py-1.5 text-sm font-medium text-slate-600 transition-colors hover:bg-slate-50"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  return (
    <button
      onClick={handleResearch}
      className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-slate-800"
    >
      {hasExisting ? "Research" : "Research EPC"}
    </button>
  );
}
