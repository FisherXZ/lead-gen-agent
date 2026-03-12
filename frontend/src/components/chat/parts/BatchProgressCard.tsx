"use client";

import { useEffect, useState, useRef } from "react";
import ConfidenceBadge from "@/components/epc/ConfidenceBadge";

const AGENT_API_URL =
  process.env.NEXT_PUBLIC_AGENT_API_URL || "http://localhost:8000";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface ProjectStatus {
  project_id: string;
  project_name: string;
  status: "waiting" | "researching" | "completed" | "skipped" | "error";
  epc_contractor?: string;
  confidence?: string;
}

interface BatchSnapshot {
  batch_id: string;
  total: number;
  completed: number;
  errors: number;
  done: boolean;
  projects: ProjectStatus[];
}

interface BatchResult {
  project_id: string;
  status: string;
  project_name?: string;
  discovery?: {
    epc_contractor: string;
    confidence: string;
  };
  reason?: string;
  error?: string;
}

interface BatchProgressCardProps {
  data: {
    results?: BatchResult[];
    total?: number;
    completed?: number;
    errors?: number;
    _batch_id?: string;
    _project_names?: Record<string, string>;
  };
  isLive?: boolean;
  input?: Record<string, unknown>;
}

// ---------------------------------------------------------------------------
// Status indicators
// ---------------------------------------------------------------------------

function StatusIcon({ status }: { status: string }) {
  switch (status) {
    case "waiting":
      return (
        <span className="inline-flex h-5 w-5 items-center justify-center">
          <span className="h-3.5 w-3.5 rounded-full border-[1.5px] border-dashed border-slate-300" />
        </span>
      );
    case "researching":
      return (
        <span className="inline-flex h-5 w-5 items-center justify-center">
          <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-blue-200 border-t-blue-500" />
        </span>
      );
    case "completed":
      return (
        <svg
          width={18}
          height={18}
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth={2.5}
          strokeLinecap="round"
          strokeLinejoin="round"
          className="text-emerald-500"
        >
          <polyline points="20 6 9 17 4 12" />
        </svg>
      );
    case "skipped":
      return (
        <svg
          width={18}
          height={18}
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth={2}
          strokeLinecap="round"
          strokeLinejoin="round"
          className="text-amber-400"
        >
          <line x1="5" y1="12" x2="19" y2="12" />
        </svg>
      );
    case "error":
      return (
        <svg
          width={18}
          height={18}
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth={2.5}
          strokeLinecap="round"
          strokeLinejoin="round"
          className="text-red-400"
        >
          <line x1="18" y1="6" x2="6" y2="18" />
          <line x1="6" y1="6" x2="18" y2="18" />
        </svg>
      );
    default:
      return null;
  }
}

const STATUS_BG: Record<string, string> = {
  waiting: "bg-slate-50 border-slate-200",
  researching: "bg-blue-50/50 border-blue-200",
  completed: "bg-emerald-50/50 border-emerald-200",
  skipped: "bg-amber-50/50 border-amber-200",
  error: "bg-red-50/50 border-red-200",
};

function statusLabel(status: string): string {
  switch (status) {
    case "waiting": return "Waiting";
    case "researching": return "Researching...";
    case "completed": return "Done";
    case "skipped": return "Skipped";
    case "error": return "Error";
    default: return status;
  }
}

// ---------------------------------------------------------------------------
// Project card (single project in the grid)
// ---------------------------------------------------------------------------

function ProjectCard({ project }: { project: ProjectStatus }) {
  const bg = STATUS_BG[project.status] || STATUS_BG.waiting;

  return (
    <div
      className={`flex items-start gap-2.5 rounded-lg border px-3 py-2.5 transition-all duration-300 ${bg}`}
    >
      <div className="mt-0.5 shrink-0">
        <StatusIcon status={project.status} />
      </div>
      <div className="min-w-0 flex-1">
        <p className="truncate text-[13px] font-medium text-slate-700">
          {project.project_name}
        </p>
        {project.status === "completed" && project.epc_contractor ? (
          <div className="mt-1 flex items-center gap-1.5">
            <span className="truncate text-xs text-slate-500">
              {project.epc_contractor}
            </span>
            {project.confidence && (
              <ConfidenceBadge confidence={project.confidence} />
            )}
          </div>
        ) : (
          <p className="mt-0.5 text-xs text-slate-400">
            {statusLabel(project.status)}
          </p>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function BatchProgressCard({
  data,
  isLive = false,
  input,
}: BatchProgressCardProps) {
  // Determine batch_id from input (during call state) or data (during result)
  const batchId =
    (input?._batch_id as string) || data._batch_id || null;

  const [liveProjects, setLiveProjects] = useState<ProjectStatus[] | null>(
    null
  );
  const [liveDone, setLiveDone] = useState(false);
  const eventSourceRef = useRef<EventSource | null>(null);

  // Subscribe to live progress when in live mode
  useEffect(() => {
    if (!isLive || !batchId || liveDone) return;

    const url = `${AGENT_API_URL}/api/batch-progress/${batchId}`;
    const es = new EventSource(url);
    eventSourceRef.current = es;

    es.onmessage = (event) => {
      try {
        const snapshot: BatchSnapshot = JSON.parse(event.data);
        setLiveProjects(snapshot.projects);
        if (snapshot.done) {
          setLiveDone(true);
          es.close();
        }
      } catch {
        // ignore parse errors
      }
    };

    es.onerror = () => {
      es.close();
    };

    return () => {
      es.close();
      eventSourceRef.current = null;
    };
  }, [isLive, batchId, liveDone]);

  // Build project list from the best available source
  let projects: ProjectStatus[];
  let total: number;
  let completedCount: number;
  let errorCount: number;

  if (liveProjects) {
    // Live SSE data
    projects = liveProjects;
    total = projects.length;
    completedCount = projects.filter(
      (p) => p.status === "completed" || p.status === "skipped" || p.status === "error"
    ).length;
    errorCount = projects.filter((p) => p.status === "error").length;
  } else if (data.results && data.results.length > 0) {
    // Final results (tool completed)
    projects = data.results.map((r) => ({
      project_id: r.project_id,
      project_name: r.project_name || r.project_id,
      status: (r.status === "started" ? "researching" : r.status) as ProjectStatus["status"],
      epc_contractor: r.discovery?.epc_contractor,
      confidence: r.discovery?.confidence,
    }));
    total = data.total || projects.length;
    completedCount = data.completed || 0;
    errorCount = data.errors || 0;
  } else if (input?._project_names) {
    // Initial state from tool input (projects known, all waiting)
    const names = input._project_names as Record<string, string>;
    const ids = (input?.project_ids as string[]) || Object.keys(names);
    projects = ids.map((id) => ({
      project_id: id,
      project_name: names[id] || id,
      status: "waiting" as const,
    }));
    total = projects.length;
    completedCount = 0;
    errorCount = 0;
  } else {
    // Fallback — nothing to show
    return null;
  }

  const progressPct = total > 0 ? (completedCount / total) * 100 : 0;

  return (
    <div className="p-4">
      {/* Header */}
      <div className="mb-3 flex items-center justify-between">
        <span className="text-sm font-medium text-slate-800">
          Batch Research
        </span>
        <span className="text-xs tabular-nums text-slate-500">
          {completedCount} / {total}
          {errorCount > 0 && (
            <span className="ml-1 text-red-500">
              ({errorCount} error{errorCount !== 1 ? "s" : ""})
            </span>
          )}
        </span>
      </div>

      {/* Progress bar */}
      <div className="mb-4 h-1.5 overflow-hidden rounded-full bg-slate-100">
        <div
          className={`h-full rounded-full transition-all duration-500 ease-out ${
            errorCount > 0 && completedCount === total
              ? "bg-red-400"
              : "bg-blue-500"
          }`}
          style={{ width: `${progressPct}%` }}
        />
      </div>

      {/* Project card grid */}
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
        {projects.map((p) => (
          <ProjectCard key={p.project_id} project={p} />
        ))}
      </div>
    </div>
  );
}
