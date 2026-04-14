"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { Project, EpcDiscovery, ConstructionStatus } from "@/lib/types";
import ConfidenceBadge from "./ConfidenceBadge";
import ResearchPlanCard from "./ResearchPlanCard";
import ActiveResearchBanner from "./ActiveResearchBanner";
import { agentFetch } from "@/lib/agent-fetch";
import {
  saveResearchState,
  getResearchState,
  clearResearchState,
} from "@/lib/research-state";

interface EpcDiscoveryDashboardProps {
  projects: Project[];
  discoveries: EpcDiscovery[];
}

type SortField =
  | "lead_score"
  | "project_name"
  | "epc_contractor"
  | "confidence"
  | "review_status"
  | "construction_status"
  | "queue_date"
  | "expected_cod";

type ResearchStatus = "idle" | "planning" | "plan_ready" | "researching" | "done" | "error";

const PAGE_SIZE = 25;


const CONSTRUCTION_LABELS: Record<string, string> = {
  unknown: "Unknown",
  pre_construction: "Pre-Construction",
  under_construction: "Under Construction",
  completed: "Completed",
  cancelled: "Cancelled",
};

const CONFIDENCE_ORDER: Record<string, number> = {
  confirmed: 0,
  likely: 1,
  possible: 2,
  unknown: 3,
};

const ERROR_MESSAGES: Record<string, string> = {
  api_key_missing: "API key not configured.",
  anthropic_error: "AI service error. Try again shortly.",
  search_tool_error: "Search tools are down. Try again later.",
  max_iterations: "Research timed out.",
  no_report: "Agent finished without findings. Try again.",
  db_error: "Database error.",
  unknown: "An unexpected error occurred.",
};

function getDiscoveryForProject(
  projectId: string,
  discoveries: EpcDiscovery[]
): EpcDiscovery | undefined {
  return discoveries.find((d) => d.project_id === projectId);
}

function formatDate(dateStr: string | null): string {
  if (!dateStr) return "—";
  const d = new Date(dateStr + "T00:00:00");
  return d.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function ScoreBadge({ score }: { score: number }) {
  let cls = "badge-red";
  if (score >= 70) cls = "badge-green";
  else if (score >= 40) cls = "badge-amber";
  return (
    <span
      className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-semibold ${cls}`}
    >
      {score}
    </span>
  );
}

function ConstructionPill({ status }: { status: ConstructionStatus }) {
  const cls: Record<string, string> = {
    pre_construction: "badge-amber",
    under_construction: "badge-amber",
    completed: "badge-green",
    cancelled: "badge-red",
    unknown: "badge-neutral",
  };
  return (
    <span
      className={`inline-block whitespace-nowrap rounded-full px-2.5 py-0.5 text-xs font-medium ${cls[status] || cls.unknown}`}
    >
      {CONSTRUCTION_LABELS[status] || "Unknown"}
    </span>
  );
}

function parseErrorMessage(status: number, body: string): string {
  try {
    const json = JSON.parse(body);
    if (json.error_category)
      return ERROR_MESSAGES[json.error_category] || json.detail || "";
    if (json.detail)
      return typeof json.detail === "string"
        ? json.detail.slice(0, 120)
        : String(json.detail);
  } catch {
    /* not JSON */
  }
  if (status === 401) return ERROR_MESSAGES.api_key_missing;
  if (status === 429) return "Rate limited. Wait a moment.";
  return `Request failed (${status})`;
}

const selectClasses = "h-8 rounded-md border border-border-default bg-surface-raised px-2 text-sm text-text-primary focus:border-border-focus focus:ring-1 focus:ring-border-focus focus:outline-none";

export default function EpcDiscoveryDashboard({
  projects,
  discoveries: initialDiscoveries,
}: EpcDiscoveryDashboardProps) {
  const [discoveries, setDiscoveries] =
    useState<EpcDiscovery[]>(initialDiscoveries);

  // Filters
  const [searchQuery, setSearchQuery] = useState("");
  const [filterState, setFilterState] = useState("");
  const [filterResearch, setFilterResearch] = useState("");
  const [filterConstruction, setFilterConstruction] = useState("");
  const [codYearFrom, setCodYearFrom] = useState(0);
  const [codYearTo, setCodYearTo] = useState(0);

  // Sort
  const [sortField, setSortField] = useState<SortField>("lead_score");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");

  // Pagination
  const [page, setPage] = useState(0);

  // Expanded research plan row
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());

  // Unique states for dropdown
  const states = useMemo(() => {
    const set = new Set<string>();
    for (const p of projects) {
      if (p.state) set.add(p.state);
    }
    return Array.from(set).sort();
  }, [projects]);

  // Filter
  const filteredProjects = useMemo(() => {
    return projects.filter((project) => {
      if (filterState && (project.state || "") !== filterState) return false;

      if (filterConstruction) {
        if ((project.construction_status || "unknown") !== filterConstruction)
          return false;
      }

      if (codYearFrom || codYearTo) {
        const codYear = project.expected_cod
          ? new Date(project.expected_cod).getFullYear()
          : null;
        if (!codYear) return false;
        if (codYearFrom && codYear < codYearFrom) return false;
        if (codYearTo && codYear > codYearTo) return false;
      }

      const discovery = getDiscoveryForProject(project.id, discoveries);
      if (filterResearch) {
        if (filterResearch === "needs_research") {
          if (discovery && discovery.review_status !== "rejected") return false;
        } else if (filterResearch === "pending") {
          if (discovery?.review_status !== "pending") return false;
        } else if (filterResearch === "reviewed") {
          if (discovery?.review_status !== "accepted") return false;
        }
      }

      if (searchQuery) {
        const q = searchQuery.toLowerCase();
        const fields = [
          project.project_name,
          project.developer,
          project.queue_id,
          project.epc_company,
          project.state,
          discovery?.epc_contractor,
        ];
        if (!fields.some((f) => (f || "").toLowerCase().includes(q)))
          return false;
      }

      return true;
    });
  }, [
    projects,
    discoveries,
    filterState,
    filterResearch,
    filterConstruction,
    codYearFrom,
    codYearTo,
    searchQuery,
  ]);

  // Sort
  const sorted = useMemo(() => {
    const arr = [...filteredProjects];
    arr.sort((a, b) => {
      let aVal: string | number | null = null;
      let bVal: string | number | null = null;

      if (
        sortField === "epc_contractor" ||
        sortField === "confidence" ||
        sortField === "review_status"
      ) {
        const aDisc = getDiscoveryForProject(a.id, discoveries);
        const bDisc = getDiscoveryForProject(b.id, discoveries);
        if (sortField === "confidence") {
          aVal = aDisc ? CONFIDENCE_ORDER[aDisc.confidence] ?? 4 : 4;
          bVal = bDisc ? CONFIDENCE_ORDER[bDisc.confidence] ?? 4 : 4;
        } else {
          aVal = aDisc?.[sortField] ?? null;
          bVal = bDisc?.[sortField] ?? null;
        }
      } else {
        aVal = a[sortField] as string | number | null;
        bVal = b[sortField] as string | number | null;
      }

      if (aVal == null && bVal == null) return 0;
      if (aVal == null) return 1;
      if (bVal == null) return -1;
      if (typeof aVal === "number" && typeof bVal === "number") {
        return sortDir === "asc" ? aVal - bVal : bVal - aVal;
      }
      const cmp = String(aVal).localeCompare(String(bVal));
      return sortDir === "asc" ? cmp : -cmp;
    });
    return arr;
  }, [filteredProjects, sortField, sortDir, discoveries]);

  // Paginate
  const totalPages = Math.max(1, Math.ceil(sorted.length / PAGE_SIZE));
  const pageProjects = sorted.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);

  function handleSort(field: SortField) {
    if (field === sortField) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortField(field);
      setSortDir(
        field === "lead_score" || field === "confidence" ? "desc" : "asc"
      );
    }
    setPage(0);
  }

  function updateFilter<T>(setter: (v: T) => void) {
    return (v: T) => {
      setter(v);
      setPage(0);
    };
  }

  function handleDiscoveryCreated(d: EpcDiscovery) {
    setDiscoveries((prev) => [d, ...prev]);
  }

  function handleScrollToProject(projectId: string) {
    // Find in sorted array (current filter set)
    let idx = sorted.findIndex((p) => p.id === projectId);

    // If filtered out, clear filters and search in full list
    if (idx === -1) {
      setFilterState("");
      setFilterResearch("");
      setFilterConstruction("");
      setCodYearFrom(0);
      setCodYearTo(0);
      setSearchQuery("");
      // After clearing filters, sorted will update — but we need the
      // unfiltered index. Projects array is the full set; sort order
      // matches lead_score desc by default after filter reset.
      // We'll find it in projects and estimate page.
      idx = projects.findIndex((p) => p.id === projectId);
    }

    if (idx === -1) return;

    const targetPage = Math.floor(idx / PAGE_SIZE);
    setPage(targetPage);
    setExpandedIds((prev) => new Set(prev).add(projectId));

    // Scroll after React renders the new page
    requestAnimationFrame(() => {
      setTimeout(() => {
        document
          .getElementById(`project-row-${projectId}`)
          ?.scrollIntoView({ behavior: "smooth", block: "center" });
      }, 50);
    });
  }

  const COLUMNS: {
    key: SortField;
    label: string;
  }[] = [
    { key: "lead_score", label: "Score" },
    { key: "project_name", label: "Project" },
    { key: "epc_contractor", label: "EPC Contractor" },
    { key: "review_status", label: "Review" },
    { key: "construction_status", label: "Construction" },
    { key: "queue_date", label: "Queue Date" },
    { key: "expected_cod", label: "Expected COD" },
  ];

  return (
    <div className="flex flex-col gap-6">
      {/* Active research banner */}
      <ActiveResearchBanner
        projects={projects}
        onScrollToProject={handleScrollToProject}
      />

      {/* Filter bar */}
      <div className="flex flex-wrap items-center gap-2 rounded-lg border border-border-subtle bg-surface-raised px-4 py-3">
        <select
          className={selectClasses}
          value={filterState}
          onChange={(e) => updateFilter(setFilterState)(e.target.value)}
        >
          <option value="">All States</option>
          {states.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>

        <select
          className={selectClasses}
          value={filterResearch}
          onChange={(e) => updateFilter(setFilterResearch)(e.target.value)}
        >
          <option value="">All Research</option>
          <option value="needs_research">Needs Research</option>
          <option value="pending">Pending Review</option>
          <option value="reviewed">Reviewed</option>
        </select>

        <select
          className={selectClasses}
          value={filterConstruction}
          onChange={(e) => updateFilter(setFilterConstruction)(e.target.value)}
        >
          <option value="">All Construction</option>
          <option value="pre_construction">Pre-Construction</option>
          <option value="under_construction">Under Construction</option>
          <option value="completed">Completed</option>
          <option value="cancelled">Cancelled</option>
          <option value="unknown">Unknown</option>
        </select>

        <select
          className={selectClasses}
          value={codYearFrom || ""}
          onChange={(e) =>
            updateFilter(setCodYearFrom)(Number(e.target.value) || 0)
          }
        >
          <option value="">COD From</option>
          {[2024, 2025, 2026, 2027, 2028, 2029, 2030].map((y) => (
            <option key={y} value={y}>
              {y}
            </option>
          ))}
        </select>

        <select
          className={selectClasses}
          value={codYearTo || ""}
          onChange={(e) =>
            updateFilter(setCodYearTo)(Number(e.target.value) || 0)
          }
        >
          <option value="">COD To</option>
          {[2024, 2025, 2026, 2027, 2028, 2029, 2030].map((y) => (
            <option key={y} value={y}>
              {y}
            </option>
          ))}
        </select>

        <input
          type="text"
          placeholder="Search..."
          className="h-8 w-56 rounded-md border border-border-default bg-surface-raised px-3 text-sm text-text-primary placeholder:text-text-tertiary focus:border-border-focus focus:ring-1 focus:ring-border-focus focus:outline-none"
          value={searchQuery}
          onChange={(e) => updateFilter(setSearchQuery)(e.target.value)}
        />
      </div>

      {/* Table */}
      <div className="overflow-hidden rounded-lg border border-border-subtle bg-surface-raised">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border-subtle bg-surface-overlay">
                {COLUMNS.map((col) => (
                  <th
                    key={col.key}
                    className="cursor-pointer select-none whitespace-nowrap px-4 py-3 text-left font-medium text-text-secondary hover:text-text-primary"
                    onClick={() => handleSort(col.key)}
                  >
                    {col.label}
                    {sortField === col.key && (
                      <span className="ml-1">
                        {sortDir === "asc" ? "↑" : "↓"}
                      </span>
                    )}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {pageProjects.length === 0 ? (
                <tr>
                  <td
                    colSpan={COLUMNS.length}
                    className="px-4 py-12 text-center text-text-tertiary"
                  >
                    No projects match the current filters.
                  </td>
                </tr>
              ) : (
                pageProjects.map((project) => {
                  const discovery = getDiscoveryForProject(
                    project.id,
                    discoveries
                  );

                  return (
                    <ProjectRow
                      key={project.id}
                      project={project}
                      discovery={discovery}
                      isExpanded={expandedIds.has(project.id)}
                      onToggleExpand={() =>
                        setExpandedIds((prev) => {
                          const next = new Set(prev);
                          if (next.has(project.id)) next.delete(project.id);
                          else next.add(project.id);
                          return next;
                        })
                      }
                      onDiscoveryCreated={handleDiscoveryCreated}
                      columnCount={COLUMNS.length}
                    />
                  );
                })
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        <div className="flex items-center justify-between border-t border-border-subtle px-4 py-3">
          <p className="text-sm text-text-secondary">
            {sorted.length > 0
              ? `Showing ${page * PAGE_SIZE + 1}–${Math.min((page + 1) * PAGE_SIZE, sorted.length)} of top ${sorted.length.toLocaleString()} by lead score`
              : "0 results"}
          </p>
          <div className="flex gap-2">
            <button
              className="rounded-md border border-border-default px-3 py-1.5 text-sm text-text-secondary transition-colors hover:bg-surface-overlay disabled:opacity-40"
              onClick={() => setPage(page - 1)}
              disabled={page === 0}
            >
              Previous
            </button>
            <button
              className="rounded-md border border-border-default px-3 py-1.5 text-sm text-text-secondary transition-colors hover:bg-surface-overlay disabled:opacity-40"
              onClick={() => setPage(page + 1)}
              disabled={page >= totalPages - 1}
            >
              Next
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

// --------------------------------------------------
// Row component with inline plan-first research
// --------------------------------------------------

const Spinner = ({ className = "h-3 w-3" }: { className?: string }) => (
  <svg className={`animate-spin ${className}`} viewBox="0 0 24 24" fill="none">
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

function ProjectRow({
  project,
  discovery,
  isExpanded,
  onToggleExpand,
  onDiscoveryCreated,
  columnCount,
}: {
  project: Project;
  discovery: EpcDiscovery | undefined;
  isExpanded: boolean;
  onToggleExpand: () => void;
  onDiscoveryCreated: (d: EpcDiscovery) => void;
  columnCount: number;
}) {
  const router = useRouter();
  const [researchStatus, setResearchStatus] = useState<ResearchStatus>("idle");
  const [plan, setPlan] = useState("");
  const [result, setResult] = useState<{
    epc_contractor?: string;
    confidence?: string;
    id?: string;
  } | null>(null);
  const [errorMessage, setErrorMessage] = useState("");

  // Restore persisted research state on mount
  useEffect(() => {
    const saved = getResearchState(project.id);
    if (!saved) return;
    if (saved.status === "plan_ready") {
      setPlan(saved.plan);
      setResearchStatus("plan_ready");
      if (!isExpanded) onToggleExpand(); // auto-expand to show plan
    } else if (saved.status === "researching") {
      // Can't resume HTTP request — downgrade to plan_ready for re-approval
      setPlan(saved.plan);
      setResearchStatus("plan_ready");
      saveResearchState(project.id, { status: "plan_ready", plan: saved.plan });
      if (!isExpanded) onToggleExpand();
    } else {
      // "planning" is stale (request is gone)
      clearResearchState(project.id);
    }
    // Only run on mount
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const reviewBadge = discovery ? (
    <span
      className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-semibold capitalize ${
        discovery.review_status === "accepted"
          ? "badge-green"
          : discovery.review_status === "pending"
            ? "badge-amber"
            : "badge-red"
      }`}
    >
      {discovery.review_status}
    </span>
  ) : (
    <span className="text-xs text-text-tertiary">—</span>
  );

  async function handleStartPlan() {
    setResearchStatus("planning");
    setErrorMessage("");
    onToggleExpand(); // expand the row
    try {
      const res = await agentFetch("/api/discover/plan", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ project_id: project.id }),
      });
      if (!res.ok) {
        setErrorMessage(parseErrorMessage(res.status, await res.text()));
        setResearchStatus("error");
        return;
      }
      const data = await res.json();
      const planText = data.plan || "No plan generated.";
      setPlan(planText);
      setResearchStatus("plan_ready");
      saveResearchState(project.id, { status: "plan_ready", plan: planText });
    } catch {
      setErrorMessage("Network error. Check your connection.");
      setResearchStatus("error");
      clearResearchState(project.id);
    }
  }

  async function handleExecute() {
    setResearchStatus("researching");
    setErrorMessage("");
    saveResearchState(project.id, { status: "researching", plan });
    try {
      const res = await agentFetch("/api/discover", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ project_id: project.id, plan }),
      });
      if (!res.ok) {
        setErrorMessage(parseErrorMessage(res.status, await res.text()));
        setResearchStatus("error");
        return;
      }
      const data = await res.json();
      setResult(data);
      setResearchStatus("done");
      clearResearchState(project.id);
      if (data.id) {
        onDiscoveryCreated(data);
      }
      router.refresh();
    } catch {
      setErrorMessage("Network error. Check your connection.");
      setResearchStatus("error");
      clearResearchState(project.id);
    }
  }

  function handleCancel() {
    setResearchStatus("idle");
    setPlan("");
    setResult(null);
    setErrorMessage("");
    clearResearchState(project.id);
    if (isExpanded) onToggleExpand();
  }

  return (
    <>
      {/* Main data row — clicks navigate to detail page */}
      <tr
        id={`project-row-${project.id}`}
        onClick={() => router.push(`/projects/${project.id}`)}
        className="cursor-pointer border-b border-border-subtle transition-colors hover:bg-surface-overlay"
      >
        {/* Score */}
        <td className="px-4 py-3">
          <ScoreBadge score={project.lead_score} />
        </td>

        {/* Project */}
        <td className="max-w-[220px] px-4 py-3">
          <div className="flex items-center gap-1.5 truncate font-medium text-text-primary">
            {project.project_name || project.queue_id}
            {discovery?.review_status === "accepted" && (
              <span
                className="inline-flex shrink-0 items-center gap-0.5 rounded-full bg-accent-amber/15 px-1.5 py-0.5 text-[10px] font-medium text-accent-amber"
                title="Hot lead — accepted discovery, contacts being found"
              >
                <svg className="h-2.5 w-2.5" viewBox="0 0 20 20" fill="currentColor">
                  <path fillRule="evenodd" d="M12.395 2.553a1 1 0 00-1.45-.385c-.345.23-.614.558-.822.88-.214.33-.403.713-.57 1.116-.334.804-.614 1.768-.84 2.734a31.365 31.365 0 00-.613 3.58 2.64 2.64 0 01-.945-1.067c-.328-.68-.398-1.534-.398-2.654A1 1 0 005.05 6.05 6.981 6.981 0 003 11a7 7 0 1011.95-4.95c-.592-.591-.98-.985-1.348-1.467-.363-.476-.724-1.063-1.207-2.03zM12.12 15.12A3 3 0 017 13s.879.5 2.5.5c0-1 .5-4 1.25-4.5.5 1 .786 1.293 1.371 1.879A2.99 2.99 0 0113 13a2.99 2.99 0 01-.879 2.121z" clipRule="evenodd" />
                </svg>
                Hot
              </span>
            )}
          </div>
          <div className="mt-0.5 flex items-center gap-2 text-xs text-text-tertiary">
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
            <span className="font-medium text-text-primary">
              {discovery.epc_contractor}
            </span>
          ) : (
            <span className="text-text-tertiary">—</span>
          )}
        </td>

        {/* Review Status */}
        <td className="px-4 py-3">{reviewBadge}</td>

        {/* Construction Status */}
        <td className="px-4 py-3">
          <ConstructionPill status={project.construction_status} />
        </td>

        {/* Queue Date */}
        <td className="whitespace-nowrap px-4 py-3 text-text-secondary">
          {formatDate(project.queue_date)}
        </td>

        {/* Expected COD */}
        <td className="whitespace-nowrap px-4 py-3 text-text-secondary">
          {formatDate(project.expected_cod)}
        </td>
      </tr>

      {/* Research action row — sits below the data row */}
      <tr className="border-b border-border-subtle">
        <td colSpan={columnCount} className="px-4 py-1.5">
          {researchStatus === "idle" && !isExpanded && !discovery && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                handleStartPlan();
              }}
              className="inline-flex items-center gap-1.5 rounded-full border border-accent-amber/30 bg-accent-amber-muted px-3 py-1 text-xs font-medium text-accent-amber transition-colors hover:border-accent-amber/50 hover:bg-accent-amber/20"
            >
              <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z" />
              </svg>
              Research EPC
            </button>
          )}
          {researchStatus === "idle" && !isExpanded && discovery && (
            <span className="inline-flex items-center gap-2">
              <ConfidenceBadge confidence={discovery.confidence} />
              <Link
                href={`/projects/${project.id}`}
                className="inline-flex items-center rounded-full border border-border-default bg-surface-overlay px-3 py-1 text-xs font-medium text-text-secondary transition-colors hover:text-text-primary"
              >
                View details
              </Link>
            </span>
          )}
          {researchStatus === "planning" && (
            <span className="inline-flex items-center gap-1.5 rounded-full border border-border-default bg-surface-overlay px-3 py-1 text-xs font-medium text-text-tertiary">
              <Spinner />
              Planning...
            </span>
          )}
          {researchStatus === "researching" && (
            <span className="inline-flex items-center gap-1.5 rounded-full border border-border-default bg-surface-overlay px-3 py-1 text-xs font-medium text-text-tertiary">
              <Spinner />
              Researching...
            </span>
          )}
          {researchStatus === "error" && (
            <span className="inline-flex items-center gap-2">
              <span className="inline-flex items-center rounded-full badge-red px-3 py-1 text-xs font-medium">
                {errorMessage}
              </span>
              <button
                onClick={handleCancel}
                className="rounded-full border border-border-default bg-surface-overlay px-3 py-1 text-xs font-medium text-text-secondary transition-colors hover:bg-surface-overlay/80"
              >
                Dismiss
              </button>
            </span>
          )}
          {researchStatus === "done" && result && (
            <span className="inline-flex items-center gap-2">
              <ConfidenceBadge confidence={result.confidence ?? "unknown"} />
              <Link
                href={`/projects/${project.id}`}
                className="inline-flex items-center rounded-full border border-border-default bg-surface-overlay px-3 py-1 text-xs font-medium text-text-secondary transition-colors hover:text-text-primary"
              >
                View details
              </Link>
            </span>
          )}
        </td>
      </tr>

      {/* Expanded plan approval card */}
      {isExpanded && (researchStatus === "plan_ready" || researchStatus === "researching") && (
        <tr className="border-b border-border-subtle">
          <td colSpan={columnCount} className="px-6 py-4">
            <ResearchPlanCard
              plan={plan}
              isResearching={researchStatus === "researching"}
              onApprove={handleExecute}
              onCancel={handleCancel}
            />
          </td>
        </tr>
      )}
    </>
  );
}
