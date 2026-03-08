"use client";

import { useState } from "react";
import { Project, EpcDiscovery, EpcFilter } from "@/lib/types";
import ConfidenceBadge from "./ConfidenceBadge";
import SourceCard from "./SourceCard";

interface ProjectPickerProps {
  projects: Project[];
  discoveries: EpcDiscovery[];
  selectedProject: Project | null;
  onSelect: (p: Project) => void;
  onResearch: (projectId: string) => void;
  isResearching: boolean;
  activeFilter: EpcFilter;
  searchQuery: string;
  checkedIds: Set<string>;
  onToggleCheck: (projectId: string) => void;
  onToggleAll: (projectIds: string[]) => void;
  filterState?: string;
  filterCodMin?: number;
  filterCodMax?: number;
  filterSource?: string;
}

function getDiscoveryForProject(
  projectId: string,
  discoveries: EpcDiscovery[]
): EpcDiscovery | undefined {
  return discoveries.find((d) => d.project_id === projectId);
}

export default function ProjectPicker({
  projects,
  discoveries,
  selectedProject,
  onSelect,
  onResearch,
  isResearching,
  activeFilter,
  searchQuery,
  checkedIds,
  onToggleCheck,
  onToggleAll,
  filterState = "",
  filterCodMin = 0,
  filterCodMax = 0,
  filterSource = "",
}: ProjectPickerProps) {
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());

  function toggleExpand(id: string) {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  // Filter projects based on active filter, search, and new filters
  const filteredProjects = projects.filter((project) => {
    // Search filter
    if (searchQuery) {
      const q = searchQuery.toLowerCase();
      const matchesName = (project.project_name || "")
        .toLowerCase()
        .includes(q);
      const matchesDeveloper = (project.developer || "")
        .toLowerCase()
        .includes(q);
      const matchesQueueId = project.queue_id.toLowerCase().includes(q);
      const matchesEpc = (project.epc_company || "")
        .toLowerCase()
        .includes(q);
      const matchesState = (project.state || "").toLowerCase().includes(q);
      if (
        !matchesName &&
        !matchesDeveloper &&
        !matchesQueueId &&
        !matchesEpc &&
        !matchesState
      )
        return false;
    }

    // Source filter
    if (filterSource && project.source !== filterSource) return false;

    // State filter
    if (filterState && (project.state || "").toLowerCase() !== filterState.toLowerCase()) return false;

    // COD year filter
    if (filterCodMin || filterCodMax) {
      const codYear = project.expected_cod
        ? new Date(project.expected_cod).getFullYear()
        : null;
      if (!codYear) return false;
      if (filterCodMin && codYear < filterCodMin) return false;
      if (filterCodMax && codYear > filterCodMax) return false;
    }

    // EPC filter
    const discovery = getDiscoveryForProject(project.id, discoveries);

    switch (activeFilter) {
      case "needs_research":
        return !discovery || discovery.review_status === "rejected";
      case "has_epc":
        return discovery?.review_status === "accepted";
      case "pending_review":
        return discovery?.review_status === "pending";
      case "all":
      default:
        return true;
    }
  });

  const filteredIds = filteredProjects.map((p) => p.id);
  const allChecked =
    filteredProjects.length > 0 &&
    filteredProjects.every((p) => checkedIds.has(p.id));

  return (
    <div className="rounded-lg border border-slate-200 bg-white">
      {/* Select-all header */}
      <div className="flex items-center gap-2 border-b border-slate-200 px-4 py-2">
        <input
          type="checkbox"
          checked={allChecked}
          onChange={() => onToggleAll(filteredIds)}
          className="h-3.5 w-3.5 rounded border-slate-300 text-blue-600 focus:ring-blue-500"
        />
        <span className="text-xs text-slate-500">
          {checkedIds.size > 0
            ? `${checkedIds.size} selected`
            : `${filteredProjects.length} projects`}
        </span>
      </div>

      <div className="max-h-[calc(100vh-380px)] overflow-y-auto">
        {filteredProjects.length === 0 ? (
          <div className="px-4 py-12 text-center text-sm text-slate-400">
            No projects match the current filters.
          </div>
        ) : (
          filteredProjects.map((project) => {
            const discovery = getDiscoveryForProject(project.id, discoveries);
            const isSelected = selectedProject?.id === project.id;
            const isChecked = checkedIds.has(project.id);

            const isExpanded = expandedIds.has(project.id);

            return (
              <div key={project.id} className="border-b border-slate-100">
                <div
                  onClick={() => onSelect(project)}
                  className={`flex cursor-pointer items-center justify-between px-4 py-3 transition-colors hover:bg-slate-50 ${
                    isSelected ? "bg-blue-50 hover:bg-blue-50" : ""
                  }`}
                >
                  {/* Expand chevron */}
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      toggleExpand(project.id);
                    }}
                    className="mr-2 shrink-0 text-slate-400 hover:text-slate-600"
                  >
                    <svg
                      className={`h-4 w-4 transition-transform ${isExpanded ? "rotate-90" : ""}`}
                      fill="none"
                      viewBox="0 0 24 24"
                      strokeWidth={2}
                      stroke="currentColor"
                    >
                      <path strokeLinecap="round" strokeLinejoin="round" d="M8.25 4.5l7.5 7.5-7.5 7.5" />
                    </svg>
                  </button>

                  {/* Checkbox */}
                  <input
                    type="checkbox"
                    checked={isChecked}
                    onClick={(e) => e.stopPropagation()}
                    onChange={() => onToggleCheck(project.id)}
                    className="mr-3 h-3.5 w-3.5 shrink-0 rounded border-slate-300 text-blue-600 focus:ring-blue-500"
                  />

                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="truncate text-sm font-medium text-slate-900">
                        {project.project_name || project.queue_id}
                      </span>
                      {project.mw_capacity && (
                        <span className="shrink-0 text-xs text-slate-400">
                          {project.mw_capacity} MW
                        </span>
                      )}
                    </div>
                    <div className="mt-0.5 flex items-center gap-2 text-xs text-slate-500">
                      {project.developer && (
                        <span className="truncate">{project.developer}</span>
                      )}
                      {project.state && (
                        <span className="shrink-0">{project.state}</span>
                      )}
                    </div>
                  </div>

                  <div className="ml-3 flex shrink-0 items-center gap-2">
                    {/* EPC status */}
                    {discovery ? (
                      <div className="flex items-center gap-1.5">
                        <span className="max-w-[120px] truncate text-xs font-medium text-slate-700">
                          {discovery.epc_contractor}
                        </span>
                        <ConfidenceBadge confidence={discovery.confidence} />
                      </div>
                    ) : (
                      <span className="text-xs text-slate-400">No EPC</span>
                    )}

                    {/* Research button */}
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        onResearch(project.id);
                      }}
                      disabled={isResearching}
                      className="rounded-md border border-slate-200 px-2.5 py-1 text-xs font-medium text-slate-600 transition-colors hover:bg-slate-50 disabled:opacity-40"
                    >
                      {isResearching ? (
                        <span className="flex items-center gap-1">
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
                          <span>...</span>
                        </span>
                      ) : (
                        "Research"
                      )}
                    </button>
                  </div>
                </div>

                {/* Expanded detail */}
                {isExpanded && (
                  <div className="border-t border-slate-100 bg-slate-50 px-10 py-3">
                    <div className="grid grid-cols-2 gap-x-6 gap-y-2 text-xs">
                      <div>
                        <span className="font-medium text-slate-500">Developer:</span>{" "}
                        <span className="text-slate-700">{project.developer || "—"}</span>
                      </div>
                      <div>
                        <span className="font-medium text-slate-500">State:</span>{" "}
                        <span className="text-slate-700">{project.state || "—"}</span>
                      </div>
                      <div>
                        <span className="font-medium text-slate-500">Source:</span>{" "}
                        <span className="text-slate-700">
                          {project.source === "gem_tracker" ? "GEM Tracker" : project.iso_region}
                        </span>
                      </div>
                      <div>
                        <span className="font-medium text-slate-500">Expected COD:</span>{" "}
                        <span className="text-slate-700">{project.expected_cod || "—"}</span>
                      </div>
                      <div>
                        <span className="font-medium text-slate-500">EPC (accepted):</span>{" "}
                        <span className="text-slate-700">{project.epc_company || "—"}</span>
                      </div>
                      <div>
                        <span className="font-medium text-slate-500">Queue Status:</span>{" "}
                        <span className="text-slate-700">{project.status || "—"}</span>
                      </div>
                    </div>
                    {discovery && discovery.sources.length > 0 && (
                      <div className="mt-3">
                        <p className="mb-1 text-xs font-medium text-slate-500">
                          Data Sources ({discovery.sources.length})
                        </p>
                        <div className="flex flex-col gap-2">
                          {discovery.sources.map((source, i) => (
                            <SourceCard key={i} source={source} />
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
