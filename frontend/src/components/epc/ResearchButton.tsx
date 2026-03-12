"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import ConfidenceBadge from "./ConfidenceBadge";
import ResearchPlanCard from "./ResearchPlanCard";
import {
  saveResearchState,
  getResearchState,
  clearResearchState,
} from "@/lib/research-state";

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
    const detail = json.detail || "";
    if (json.error_category) {
      return ERROR_MESSAGES[json.error_category] || detail;
    }
    if (status === 401) return ERROR_MESSAGES.api_key_missing;
    if (status === 409) return "Already has an accepted EPC discovery.";
    if (status === 429) return "Rate limited. Please wait a moment and retry.";
    if (status === 503) return "Service unavailable. Check configuration.";
    if (detail)
      return typeof detail === "string" ? detail.slice(0, 120) : String(detail);
  } catch {
    // Not JSON
  }
  if (status === 401) return ERROR_MESSAGES.api_key_missing;
  if (status === 429) return "Rate limited. Please wait a moment and retry.";
  return `Request failed (${status})`;
}

type Status =
  | "idle"
  | "planning"
  | "plan_ready"
  | "researching"
  | "done"
  | "error";

interface DiscoveryResult {
  id?: string;
  epc_contractor?: string;
  confidence?: string;
  source_count?: number;
  error_category?: string;
  error_message?: string;
}

const Spinner = () => (
  <svg className="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none">
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
);

export default function ResearchButton({
  projectId,
  hasExisting,
}: {
  projectId: string;
  hasExisting: boolean;
}) {
  const [status, setStatus] = useState<Status>("idle");
  const [plan, setPlan] = useState<string>("");
  const [result, setResult] = useState<DiscoveryResult | null>(null);
  const [errorMessage, setErrorMessage] = useState("");
  const router = useRouter();

  // Restore persisted research state on mount
  useEffect(() => {
    const saved = getResearchState(projectId);
    if (!saved) return;
    if (saved.status === "plan_ready") {
      setPlan(saved.plan);
      setStatus("plan_ready");
    } else if (saved.status === "researching") {
      // Can't resume HTTP request — downgrade to plan_ready for re-approval
      setPlan(saved.plan);
      setStatus("plan_ready");
      saveResearchState(projectId, { status: "plan_ready", plan: saved.plan });
    }
    // "planning" is stale — ignore
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Step 1: Get a research plan
  async function handlePlan() {
    setStatus("planning");
    setErrorMessage("");
    try {
      const res = await fetch(`${AGENT_API_URL}/api/discover/plan`, {
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
      const data = await res.json();
      const planText = data.plan || "No plan generated.";
      setPlan(planText);
      setStatus("plan_ready");
      saveResearchState(projectId, { status: "plan_ready", plan: planText });
    } catch {
      setErrorMessage("Network error. Check your connection and try again.");
      setStatus("error");
      clearResearchState(projectId);
    }
  }

  // Step 2: Execute the approved plan
  async function handleExecute() {
    setStatus("researching");
    setErrorMessage("");
    saveResearchState(projectId, { status: "researching", plan });
    try {
      const res = await fetch(`${AGENT_API_URL}/api/discover`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ project_id: projectId, plan }),
      });
      if (!res.ok) {
        const errText = await res.text();
        setErrorMessage(parseErrorMessage(res.status, errText));
        setStatus("error");
        return;
      }
      const data = await res.json();
      setResult(data);
      setStatus("done");
      clearResearchState(projectId);
      router.refresh();
    } catch {
      setErrorMessage("Network error. Check your connection and try again.");
      setStatus("error");
      clearResearchState(projectId);
    }
  }

  // Open research context in chat
  async function handleReviewInChat() {
    if (!result?.id) return;
    try {
      const res = await fetch(
        `${AGENT_API_URL}/api/discover/handoff?discovery_id=${result.id}`,
        { method: "POST" }
      );
      if (res.ok) {
        const data = await res.json();
        router.push(`/chat?conversation=${data.conversation_id}`);
      }
    } catch {
      // Best effort
    }
  }

  function handleReset() {
    setStatus("idle");
    setPlan("");
    setResult(null);
    setErrorMessage("");
    clearResearchState(projectId);
  }

  // --- Renders ---

  if (status === "idle") {
    return (
      <button
        onClick={handlePlan}
        className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-slate-800"
      >
        {hasExisting ? "Re-research" : "Research EPC"}
      </button>
    );
  }

  if (status === "planning") {
    return (
      <button
        disabled
        className="inline-flex items-center gap-2 rounded-md bg-slate-100 px-4 py-2 text-sm font-medium text-slate-400"
      >
        <Spinner />
        Planning research...
      </button>
    );
  }

  if (status === "plan_ready") {
    return (
      <ResearchPlanCard
        plan={plan}
        isResearching={false}
        onApprove={handleExecute}
        onCancel={handleReset}
      />
    );
  }

  if (status === "researching") {
    return (
      <button
        disabled
        className="inline-flex items-center gap-2 rounded-md bg-slate-100 px-4 py-2 text-sm font-medium text-slate-400"
      >
        <Spinner />
        Researching...
      </button>
    );
  }

  if (status === "done" && result) {
    const isUnknown =
      !result.epc_contractor || result.epc_contractor === "Unknown";
    return (
      <div className="max-w-md space-y-2">
        <div className="flex items-center gap-2">
          <svg
            className="h-4 w-4 text-emerald-500"
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
          <span className="text-sm font-medium text-slate-700">
            {isUnknown
              ? "No EPC found"
              : result.epc_contractor}
          </span>
          {result.confidence && (
            <ConfidenceBadge confidence={result.confidence} size="sm" />
          )}
        </div>
        {result.error_category && (
          <p className="text-xs text-amber-600">
            {ERROR_MESSAGES[result.error_category] || result.error_message}
          </p>
        )}
        <div className="flex gap-2">
          {result.id && (
            <button
              onClick={handleReviewInChat}
              className="rounded-md border border-amber-200 bg-amber-50 px-3 py-1.5 text-xs font-medium text-amber-700 transition-colors hover:bg-amber-100"
            >
              Review in Chat
            </button>
          )}
          <button
            onClick={handleReset}
            className="rounded-md border border-slate-200 px-3 py-1.5 text-xs font-medium text-slate-500 transition-colors hover:bg-slate-50"
          >
            Done
          </button>
        </div>
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
            onClick={handleReset}
            className="rounded-md border border-slate-200 px-3 py-1.5 text-sm font-medium text-slate-600 transition-colors hover:bg-slate-50"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  return null;
}
