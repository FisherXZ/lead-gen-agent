"use client";

import { useCallback, useMemo, useRef, useState } from "react";
import { Project, EpcDiscovery, EpcFilter } from "@/lib/types";
import ConfidenceBadge from "./ConfidenceBadge";
import SourceCard from "./SourceCard";

interface EpcDiscoveryDashboardProps {
  projects: Project[];
  discoveries: EpcDiscovery[];
}

interface BatchProgress {
  completed: number;
  total: number;
  currentProject: string;
}

const AGENT_API_URL =
  process.env.NEXT_PUBLIC_AGENT_API_URL || "http://localhost:8000";

const FILTER_TABS: { key: EpcFilter; label: string }[] = [
  { key: "all", label: "All" },
  { key: "needs_research", label: "Needs Research" },
  { key: "has_epc", label: "Has EPC" },
  { key: "pending_review", label: "Pending Review" },
];

function getDiscoveryForProject(
  projectId: string,
  discoveries: EpcDiscovery[]
): EpcDiscovery | undefined {
  return discoveries.find((d) => d.project_id === projectId);
}

export default function EpcDiscoveryDashboard({
  projects,
  discoveries: initialDiscoveries,
}: EpcDiscoveryDashboardProps) {
  const [discoveries, setDiscoveries] =
    useState<EpcDiscovery[]>(initialDiscoveries);
  const [activeFilter, setActiveFilter] = useState<EpcFilter>("all");
  const [searchQuery, setSearchQuery] = useState("");
  const [filterSource, setFilterSource] = useState("");
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());
  const [isResearching, setIsResearching] = useState(false);
  const [researchingId, setResearchingId] = useState<string | null>(null);

  // Batch state
  const [checkedIds, setCheckedIds] = useState<Set<string>>(new Set());
  const [batchProgress, setBatchProgress] = useState<BatchProgress | null>(
    null
  );
  const abortRef = useRef<AbortController | null>(null);

  function toggleExpand(id: string) {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  // Filter + search
  const filteredProjects = useMemo(() => {
    return projects.filter((project) => {
      // Source filter
      if (filterSource && project.source !== filterSource) return false;

      if (searchQuery) {
        const q = searchQuery.toLowerCase();
        const fields = [
          project.project_name,
          project.developer,
          project.queue_id,
          project.epc_company,
          project.state,
        ];
        if (!fields.some((f) => (f || "").toLowerCase().includes(q)))
          return false;
      }

      const discovery = getDiscoveryForProject(project.id, discoveries);

      switch (activeFilter) {
        case "needs_research":
          return !discovery || discovery.review_status === "rejected";
        case "has_epc":
          return discovery?.review_status === "accepted";
        case "pending_review":
          return discovery?.review_status === "pending";
        default:
          return true;
      }
    });
  }, [projects, discoveries, activeFilter, searchQuery, filterSource]);

  // Tab counts
  const tabCounts = useMemo(() => {
    const counts = { all: projects.length, needs_research: 0, has_epc: 0, pending_review: 0 };
    for (const p of projects) {
      const d = getDiscoveryForProject(p.id, discoveries);
      if (!d || d.review_status === "rejected") counts.needs_research++;
      else if (d.review_status === "accepted") counts.has_epc++;
      else if (d.review_status === "pending") counts.pending_review++;
    }
    return counts;
  }, [projects, discoveries]);

  // Checkbox handlers
  const handleToggleCheck = useCallback((projectId: string) => {
    setCheckedIds((prev) => {
      const next = new Set(prev);
      if (next.has(projectId)) next.delete(projectId);
      else next.add(projectId);
      return next;
    });
  }, []);

  const filteredIds = useMemo(
    () => filteredProjects.map((p) => p.id),
    [filteredProjects]
  );
  const allChecked =
    filteredProjects.length > 0 &&
    filteredProjects.every((p) => checkedIds.has(p.id));

  function handleToggleAll() {
    if (allChecked) {
      setCheckedIds((prev) => {
        const next = new Set(prev);
        for (const id of filteredIds) next.delete(id);
        return next;
      });
    } else {
      setCheckedIds((prev) => {
        const next = new Set(prev);
        for (const id of filteredIds) next.add(id);
        return next;
      });
    }
  }

  // Single research
  async function handleResearch(projectId: string) {
    setIsResearching(true);
    setResearchingId(projectId);
    try {
      const res = await fetch(`${AGENT_API_URL}/api/discover`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ project_id: projectId }),
      });

      if (!res.ok) {
        const errText = await res.text();
        throw new Error(errText || `Request failed with status ${res.status}`);
      }

      const newDiscovery: EpcDiscovery = await res.json();
      setDiscoveries((prev) => [newDiscovery, ...prev]);
      // Auto-expand to show the result
      setExpandedIds((prev) => new Set(prev).add(projectId));
    } catch (err) {
      console.error("Research failed:", err);
      alert(
        `Research failed: ${err instanceof Error ? err.message : "Unknown error"}`
      );
    } finally {
      setIsResearching(false);
      setResearchingId(null);
    }
  }

  // Batch research via SSE
  async function handleBatchResearch() {
    const ids = Array.from(checkedIds);
    if (ids.length === 0) return;

    const abort = new AbortController();
    abortRef.current = abort;
    setBatchProgress({ completed: 0, total: ids.length, currentProject: "" });
    setIsResearching(true);

    try {
      const res = await fetch(`${AGENT_API_URL}/api/discover/batch`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ project_ids: ids }),
        signal: abort.signal,
      });

      if (!res.ok) {
        const errText = await res.text();
        throw new Error(errText || `Batch request failed: ${res.status}`);
      }

      const reader = res.body?.getReader();
      if (!reader) throw new Error("No response body");

      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          const jsonStr = line.slice(6);
          if (!jsonStr) continue;

          try {
            const event = JSON.parse(jsonStr);

            if (event.type === "started") {
              setBatchProgress({
                completed: event.completed,
                total: event.total,
                currentProject: event.project_name || "",
              });
            } else if (event.type === "completed") {
              setBatchProgress({
                completed: event.completed,
                total: event.total,
                currentProject: "",
              });
              if (event.discovery) {
                setDiscoveries((prev) => [event.discovery, ...prev]);
              }
            } else if (event.type === "skipped" || event.type === "error") {
              setBatchProgress({
                completed: event.completed,
                total: event.total,
                currentProject: "",
              });
            }
          } catch {
            // skip malformed JSON
          }
        }
      }

      setCheckedIds(new Set());
    } catch (err) {
      if ((err as Error).name !== "AbortError") {
        console.error("Batch research failed:", err);
        alert(
          `Batch failed: ${err instanceof Error ? err.message : "Unknown error"}`
        );
      }
    } finally {
      setIsResearching(false);
      setBatchProgress(null);
      abortRef.current = null;
    }
  }

  // Review handler
  async function handleReview(
    discoveryId: string,
    action: "accepted" | "rejected"
  ) {
    try {
      const res = await fetch(
        `${AGENT_API_URL}/api/discover/${discoveryId}/review`,
        {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ action }),
        }
      );

      if (!res.ok) {
        const errText = await res.text();
        throw new Error(errText || `Request failed with status ${res.status}`);
      }

      setDiscoveries((prev) =>
        prev.map((d) =>
          d.id === discoveryId ? { ...d, review_status: action } : d
        )
      );
    } catch (err) {
      console.error("Review failed:", err);
      alert(
        `Review failed: ${err instanceof Error ? err.message : "Unknown error"}`
      );
    }
  }

  return (
    <div className="flex flex-col gap-4">
      {/* Toolbar: filters + search + batch */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex gap-1">
          {FILTER_TABS.map((tab) => (
            <button
              key={tab.key}
              onClick={() => setActiveFilter(tab.key)}
              className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
                activeFilter === tab.key
                  ? "bg-slate-900 text-white"
                  : "bg-white text-slate-600 hover:bg-slate-100"
              }`}
            >
              {tab.label}
              <span className="ml-1.5 text-xs opacity-60">
                {tabCounts[tab.key].toLocaleString()}
              </span>
            </button>
          ))}
        </div>
        <div className="flex items-center gap-2">
          <select
            className="h-8 rounded-md border border-slate-200 bg-white px-2 text-sm text-slate-900"
            value={filterSource}
            onChange={(e) => setFilterSource(e.target.value)}
          >
            <option value="">All Sources</option>
            <option value="iso_queue">ISO Queues</option>
            <option value="gem_tracker">GEM Tracker</option>
          </select>
          {checkedIds.size > 0 && (
            <button
              onClick={handleBatchResearch}
              disabled={isResearching}
              className="rounded-md bg-blue-600 px-3 py-1.5 text-sm font-medium text-white transition-colors hover:bg-blue-700 disabled:opacity-50"
            >
              Research Selected ({checkedIds.size})
            </button>
          )}
          <input
            type="text"
            placeholder="Search..."
            className="h-8 w-56 rounded-md border border-slate-200 bg-white px-3 text-sm text-slate-900"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
        </div>
      </div>

      {/* Batch progress */}
      {batchProgress && (
        <div className="rounded-lg border border-blue-200 bg-blue-50 p-3">
          <div className="mb-1.5 flex items-center justify-between text-sm">
            <span className="font-medium text-blue-900">
              Batch: {batchProgress.completed}/{batchProgress.total}
            </span>
            {batchProgress.currentProject && (
              <span className="text-blue-600 text-xs">
                Researching: {batchProgress.currentProject}
              </span>
            )}
          </div>
          <div className="h-1.5 overflow-hidden rounded-full bg-blue-200">
            <div
              className="h-full rounded-full bg-blue-600 transition-all duration-300"
              style={{
                width: `${batchProgress.total > 0 ? (batchProgress.completed / batchProgress.total) * 100 : 0}%`,
              }}
            />
          </div>
        </div>
      )}

      {/* Table */}
      <div className="overflow-hidden rounded-lg border border-slate-200 bg-white">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-200 bg-slate-50">
              <th className="w-10 px-3 py-3">
                <input
                  type="checkbox"
                  checked={allChecked}
                  onChange={handleToggleAll}
                  className="h-3.5 w-3.5 rounded border-slate-300 text-blue-600 focus:ring-blue-500"
                />
              </th>
              <th className="px-4 py-3 text-left font-medium text-slate-600">
                Project
              </th>
              <th className="px-4 py-3 text-left font-medium text-slate-600">
                EPC Contractor
              </th>
              <th className="px-4 py-3 text-left font-medium text-slate-600">
                Confidence
              </th>
              <th className="px-4 py-3 text-left font-medium text-slate-600">
                Status
              </th>
              <th className="w-28 px-4 py-3 text-right font-medium text-slate-600">
                Action
              </th>
            </tr>
          </thead>
          <tbody>
            {filteredProjects.length === 0 ? (
              <tr>
                <td
                  colSpan={6}
                  className="px-4 py-12 text-center text-slate-400"
                >
                  No projects match the current filters.
                </td>
              </tr>
            ) : (
              filteredProjects.map((project) => {
                const discovery = getDiscoveryForProject(
                  project.id,
                  discoveries
                );
                const isExpanded = expandedIds.has(project.id);
                const isChecked = checkedIds.has(project.id);
                const isThisResearching =
                  isResearching && researchingId === project.id;

                return (
                  <ResearchRow
                    key={project.id}
                    project={project}
                    discovery={discovery}
                    isExpanded={isExpanded}
                    isChecked={isChecked}
                    isResearching={isThisResearching}
                    batchRunning={isResearching}
                    onToggleExpand={() => toggleExpand(project.id)}
                    onToggleCheck={() => handleToggleCheck(project.id)}
                    onResearch={() => handleResearch(project.id)}
                    onReview={handleReview}
                  />
                );
              })
            )}
          </tbody>
        </table>
      </div>

      {/* Result count */}
      <p className="text-xs text-slate-400">
        {filteredProjects.length.toLocaleString()} projects
      </p>
    </div>
  );
}

// --------------------------------------------------
// Inline row component
// --------------------------------------------------

function ResearchRow({
  project,
  discovery,
  isExpanded,
  isChecked,
  isResearching,
  batchRunning,
  onToggleExpand,
  onToggleCheck,
  onResearch,
  onReview,
}: {
  project: Project;
  discovery: EpcDiscovery | undefined;
  isExpanded: boolean;
  isChecked: boolean;
  isResearching: boolean;
  batchRunning: boolean;
  onToggleExpand: () => void;
  onToggleCheck: () => void;
  onResearch: () => void;
  onReview: (id: string, action: "accepted" | "rejected") => void;
}) {
  const reviewBadge = discovery ? (
    <span
      className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-semibold capitalize ${
        discovery.review_status === "accepted"
          ? "bg-emerald-100 text-emerald-700"
          : discovery.review_status === "pending"
            ? "bg-amber-100 text-amber-700"
            : "bg-red-100 text-red-700"
      }`}
    >
      {discovery.review_status}
    </span>
  ) : (
    <span className="text-xs text-slate-300">—</span>
  );

  return (
    <>
      <tr
        onClick={discovery ? onToggleExpand : undefined}
        className={`border-b border-slate-100 transition-colors ${
          discovery ? "cursor-pointer hover:bg-slate-50" : ""
        } ${isExpanded ? "bg-slate-50" : ""}`}
      >
        {/* Checkbox */}
        <td className="px-3 py-3">
          <input
            type="checkbox"
            checked={isChecked}
            onClick={(e) => e.stopPropagation()}
            onChange={onToggleCheck}
            className="h-3.5 w-3.5 rounded border-slate-300 text-blue-600 focus:ring-blue-500"
          />
        </td>

        {/* Project */}
        <td className="max-w-[220px] px-4 py-3">
          <div className="truncate font-medium text-slate-900">
            {project.project_name || project.queue_id}
          </div>
          <div className="mt-0.5 flex items-center gap-2 text-xs text-slate-400">
            {project.developer && (
              <span className="truncate">{project.developer}</span>
            )}
            {project.mw_capacity && (
              <span className="shrink-0">{project.mw_capacity} MW</span>
            )}
            {project.state && (
              <span className="shrink-0">{project.state}</span>
            )}
          </div>
        </td>

        {/* EPC Contractor */}
        <td className="px-4 py-3">
          {discovery ? (
            <span className="font-medium text-slate-900">
              {discovery.epc_contractor}
            </span>
          ) : (
            <span className="text-slate-300">—</span>
          )}
        </td>

        {/* Confidence */}
        <td className="px-4 py-3">
          {discovery ? (
            <ConfidenceBadge confidence={discovery.confidence} />
          ) : (
            <span className="text-slate-300">—</span>
          )}
        </td>

        {/* Review Status */}
        <td className="px-4 py-3">{reviewBadge}</td>

        {/* Action */}
        <td className="px-4 py-3 text-right">
          {isResearching ? (
            <span className="inline-flex items-center gap-1 rounded-md border border-slate-200 px-2.5 py-1 text-xs font-medium text-slate-400">
              <svg
                className="h-3 w-3 animate-spin"
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
              Researching
            </span>
          ) : discovery ? (
            <button
              onClick={(e) => {
                e.stopPropagation();
                onResearch();
              }}
              disabled={batchRunning}
              className="group relative inline-flex items-center gap-1.5 rounded-md border border-emerald-200 bg-emerald-50 px-2.5 py-1 text-xs font-medium text-emerald-600 transition-colors hover:border-slate-300 hover:bg-slate-50 hover:text-slate-600 disabled:opacity-40"
              title="Run research again"
            >
              <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" />
              </svg>
              <span className="group-hover:hidden">Done</span>
              <span className="hidden group-hover:inline">Research</span>
            </button>
          ) : (
            <button
              onClick={(e) => {
                e.stopPropagation();
                onResearch();
              }}
              disabled={batchRunning}
              className="rounded-md border border-slate-200 px-2.5 py-1 text-xs font-medium text-slate-600 transition-colors hover:bg-slate-100 disabled:opacity-40"
            >
              Research
            </button>
          )}
        </td>
      </tr>

      {/* Expanded detail row */}
      {isExpanded && discovery && (
        <tr className="border-b border-slate-100">
          <td colSpan={6} className="bg-slate-50 px-8 py-5">
            <div className="flex flex-col gap-4 max-w-3xl">
              {/* Reasoning */}
              {discovery.reasoning && (
                <div>
                  <p className="mb-1 text-xs font-semibold uppercase tracking-wider text-slate-400">
                    Reasoning
                  </p>
                  <p className="text-sm leading-relaxed text-slate-600">
                    {discovery.reasoning}
                  </p>
                </div>
              )}

              {/* Sources */}
              {discovery.sources.length > 0 && (
                <div>
                  <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-400">
                    Sources ({discovery.sources.length})
                  </p>
                  <div className="grid gap-2 sm:grid-cols-2">
                    {discovery.sources.map((source, i) => (
                      <SourceCard key={i} source={source} />
                    ))}
                  </div>
                </div>
              )}

              {/* Review actions */}
              {discovery.review_status === "pending" && (
                <div className="flex items-center gap-2 pt-1">
                  <button
                    onClick={() => onReview(discovery.id, "accepted")}
                    className="rounded-md bg-emerald-600 px-4 py-1.5 text-sm font-medium text-white transition-colors hover:bg-emerald-700"
                  >
                    Accept
                  </button>
                  <button
                    onClick={() => onReview(discovery.id, "rejected")}
                    className="rounded-md border border-slate-300 px-4 py-1.5 text-sm font-medium text-slate-600 transition-colors hover:bg-slate-100"
                  >
                    Reject
                  </button>
                </div>
              )}
            </div>
          </td>
        </tr>
      )}
    </>
  );
}
