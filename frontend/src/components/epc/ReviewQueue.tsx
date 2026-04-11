"use client";

import React, { useMemo, useState } from "react";
import ConfidenceBadge from "@/components/epc/ConfidenceBadge";
import ReasoningCard from "@/components/epc/ReasoningCard";
import { PendingDiscoveryWithProject } from "@/lib/types";
import { agentFetch } from "@/lib/agent-fetch";

interface ReviewQueueProps {
  initialDiscoveries: PendingDiscoveryWithProject[];
}

const CONFIDENCE_ORDER: Record<string, number> = {
  confirmed: 0,
  likely: 1,
  possible: 2,
  unknown: 3,
};

export default function ReviewQueue({ initialDiscoveries }: ReviewQueueProps) {
  const [discoveries, setDiscoveries] =
    useState<PendingDiscoveryWithProject[]>(initialDiscoveries);
  const [rejectingId, setRejectingId] = useState<string | null>(null);
  const [rejectReason, setRejectReason] = useState("");
  const [loadingId, setLoadingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());
  const [filterState, setFilterState] = useState("");
  const [filterConfidence, setFilterConfidence] = useState("");
  const [searchQuery, setSearchQuery] = useState("");

  type SortField =
    | "project_name"
    | "state"
    | "epc_contractor"
    | "confidence"
    | "created_at";
  const [sortField, setSortField] = useState<SortField>("created_at");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");

  function handleSort(field: SortField) {
    if (field === sortField) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortField(field);
      setSortDir(field === "created_at" ? "desc" : "asc");
    }
  }

  const availableStates = useMemo(() => {
    const set = new Set<string>();
    for (const d of discoveries) {
      if (d.project?.state) set.add(d.project.state);
    }
    return Array.from(set).sort();
  }, [discoveries]);

  const visibleDiscoveries = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    const filtered = discoveries.filter((d) => {
      const p = d.project || {};
      if (filterState && (p.state || "") !== filterState) return false;
      if (filterConfidence && d.confidence !== filterConfidence) return false;
      if (q) {
        const haystack = [p.project_name, p.developer, d.epc_contractor]
          .filter(Boolean)
          .join(" ")
          .toLowerCase();
        if (!haystack.includes(q)) return false;
      }
      return true;
    });

    const sorted = [...filtered].sort((a, b) => {
      let av: string | number = "";
      let bv: string | number = "";
      switch (sortField) {
        case "project_name":
          av = a.project?.project_name || "";
          bv = b.project?.project_name || "";
          break;
        case "state":
          av = a.project?.state || "";
          bv = b.project?.state || "";
          break;
        case "epc_contractor":
          av = a.epc_contractor || "";
          bv = b.epc_contractor || "";
          break;
        case "confidence":
          av = CONFIDENCE_ORDER[a.confidence] ?? 4;
          bv = CONFIDENCE_ORDER[b.confidence] ?? 4;
          break;
        case "created_at":
          av = a.created_at ? Date.parse(a.created_at) : 0;
          bv = b.created_at ? Date.parse(b.created_at) : 0;
          break;
      }
      if (av < bv) return sortDir === "asc" ? -1 : 1;
      if (av > bv) return sortDir === "asc" ? 1 : -1;
      return 0;
    });

    return sorted;
  }, [
    discoveries,
    filterState,
    filterConfidence,
    searchQuery,
    sortField,
    sortDir,
  ]);

  function toggleExpand(id: string) {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function handleAccept(id: string) {
    setLoadingId(id);
    setError(null);
    try {
      const res = await agentFetch(`/api/discover/${id}/review`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "accepted" }),
      });
      if (res.ok) {
        setDiscoveries((prev) => prev.filter((d) => d.id !== id));
      } else {
        setError("Failed to accept discovery. Please try again.");
      }
    } catch (err) {
      console.error("Accept failed:", err);
      setError("Failed to accept discovery. Please try again.");
    } finally {
      setLoadingId(null);
    }
  }

  async function handleReject(id: string) {
    if (!rejectReason.trim()) return;
    setLoadingId(id);
    setError(null);
    try {
      const res = await agentFetch(`/api/discover/${id}/review`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "rejected", reason: rejectReason.trim() }),
      });
      if (res.ok) {
        setDiscoveries((prev) => prev.filter((d) => d.id !== id));
        setRejectingId(null);
        setRejectReason("");
      } else {
        setError("Failed to reject discovery. Please try again.");
      }
    } catch (err) {
      console.error("Reject failed:", err);
      setError("Failed to reject discovery. Please try again.");
    } finally {
      setLoadingId(null);
    }
  }

  if (discoveries.length === 0) {
    return (
      <div className="rounded-lg border border-border-subtle bg-surface-raised p-12 text-center">
        <p className="text-sm text-text-secondary">
          No pending discoveries to review. New discoveries will appear here
          after the agent researches projects.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <p className="mr-auto text-sm text-text-secondary">
          {visibleDiscoveries.length} of {discoveries.length} pending{" "}
          {discoveries.length === 1 ? "discovery" : "discoveries"}
        </p>
        <label className="flex items-center gap-1.5 text-xs text-text-tertiary">
          State
          <select
            aria-label="State"
            className="h-8 rounded-md border border-border-default bg-surface-raised px-2 text-sm text-text-primary focus:border-border-focus focus:ring-1 focus:ring-border-focus focus:outline-none"
            value={filterState}
            onChange={(e) => setFilterState(e.target.value)}
          >
            <option value="">All</option>
            {availableStates.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </label>
        <label className="flex items-center gap-1.5 text-xs text-text-tertiary">
          Confidence
          <select
            aria-label="Confidence"
            className="h-8 rounded-md border border-border-default bg-surface-raised px-2 text-sm text-text-primary focus:border-border-focus focus:ring-1 focus:ring-border-focus focus:outline-none"
            value={filterConfidence}
            onChange={(e) => setFilterConfidence(e.target.value)}
          >
            <option value="">All</option>
            <option value="confirmed">Confirmed</option>
            <option value="likely">Likely</option>
            <option value="possible">Possible</option>
            <option value="unknown">Unknown</option>
          </select>
        </label>
        <input
          type="text"
          placeholder="Search project, developer, EPC…"
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className="h-8 w-56 rounded-md border border-border-default bg-surface-raised px-3 text-sm text-text-primary placeholder:text-text-tertiary focus:border-border-focus focus:ring-1 focus:ring-border-focus focus:outline-none"
        />
      </div>

      {error && (
        <div className="rounded-lg badge-red border border-status-red/20 px-4 py-3 text-sm">
          {error}
        </div>
      )}

      <div className="overflow-hidden rounded-lg border border-border-subtle bg-surface-raised">
        <table className="min-w-full divide-y divide-border-subtle">
          <thead className="bg-surface-overlay">
            <tr>
              <th
                onClick={() => handleSort("project_name")}
                className="cursor-pointer select-none px-4 py-3 text-left text-xs font-medium uppercase tracking-wide text-text-tertiary hover:text-text-secondary"
              >
                Project
                {sortField === "project_name" && (
                  <span className="ml-1">{sortDir === "asc" ? "↑" : "↓"}</span>
                )}
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wide text-text-tertiary">
                Developer
              </th>
              <th className="px-4 py-3 text-right text-xs font-medium uppercase tracking-wide text-text-tertiary">
                MW
              </th>
              <th
                onClick={() => handleSort("state")}
                className="cursor-pointer select-none px-4 py-3 text-left text-xs font-medium uppercase tracking-wide text-text-tertiary hover:text-text-secondary"
              >
                State
                {sortField === "state" && (
                  <span className="ml-1">{sortDir === "asc" ? "↑" : "↓"}</span>
                )}
              </th>
              <th
                onClick={() => handleSort("epc_contractor")}
                className="cursor-pointer select-none px-4 py-3 text-left text-xs font-medium uppercase tracking-wide text-text-tertiary hover:text-text-secondary"
              >
                EPC Contractor
                {sortField === "epc_contractor" && (
                  <span className="ml-1">{sortDir === "asc" ? "↑" : "↓"}</span>
                )}
              </th>
              <th
                onClick={() => handleSort("confidence")}
                className="cursor-pointer select-none px-4 py-3 text-left text-xs font-medium uppercase tracking-wide text-text-tertiary hover:text-text-secondary"
              >
                Confidence
                {sortField === "confidence" && (
                  <span className="ml-1">{sortDir === "asc" ? "↑" : "↓"}</span>
                )}
              </th>
              <th
                onClick={() => handleSort("created_at")}
                className="cursor-pointer select-none px-4 py-3 text-left text-xs font-medium uppercase tracking-wide text-text-tertiary hover:text-text-secondary"
              >
                Created
                {sortField === "created_at" && (
                  <span className="ml-1">{sortDir === "asc" ? "↑" : "↓"}</span>
                )}
              </th>
              <th className="px-4 py-3 text-right text-xs font-medium uppercase tracking-wide text-text-tertiary">
                Actions
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border-subtle">
            {visibleDiscoveries.map((d) => {
              const project = d.project || {};
              const isRejecting = rejectingId === d.id;
              const isLoading = loadingId === d.id;
              const isExpanded = expandedIds.has(d.id);
              const allLow =
                d.sources?.length > 0 &&
                d.sources.every((s) => s.reliability === "low");

              return (
                <React.Fragment key={d.id}>
                  <tr
                    onClick={() => toggleExpand(d.id)}
                    className={`cursor-pointer transition-colors ${
                      isExpanded ? "bg-surface-overlay" : "hover:bg-surface-overlay"
                    }`}
                  >
                    <td className="px-4 py-3 text-sm font-medium text-text-primary">
                      {project.project_name || "Unnamed"}
                    </td>
                    <td className="px-4 py-3 text-sm text-text-secondary">
                      {project.developer || "\u2014"}
                    </td>
                    <td className="px-4 py-3 text-right text-sm text-text-secondary">
                      {project.mw_capacity ?? "\u2014"}
                    </td>
                    <td className="px-4 py-3 text-sm text-text-secondary">
                      {project.state || "\u2014"}
                    </td>
                    <td className="px-4 py-3 text-sm font-medium text-text-primary">
                      {d.epc_contractor}
                    </td>
                    <td className="px-4 py-3">
                      <ConfidenceBadge
                        confidence={d.confidence}
                        sourceCount={d.source_count ?? d.sources?.length}
                        warning={allLow ? "Unverified" : undefined}
                      />
                    </td>
                    <td className="px-4 py-3 text-sm text-text-tertiary">
                      {d.created_at
                        ? new Date(d.created_at).toLocaleDateString()
                        : "\u2014"}
                    </td>
                    <td className="px-4 py-3 text-right">
                      {isRejecting ? (
                        <div
                          className="flex flex-col items-end gap-2"
                          onClick={(e) => e.stopPropagation()}
                        >
                          <textarea
                            value={rejectReason}
                            onChange={(e) => setRejectReason(e.target.value)}
                            placeholder="Reason for rejection (required)"
                            className="w-64 rounded-md border border-border-default bg-surface-overlay px-2 py-1.5 text-xs text-text-primary placeholder:text-text-tertiary focus:border-border-focus focus:outline-none focus:ring-1 focus:ring-border-focus"
                            rows={2}
                          />
                          <div className="flex gap-1.5">
                            <button
                              onClick={() => {
                                setRejectingId(null);
                                setRejectReason("");
                              }}
                              className="rounded-md px-2.5 py-1 text-xs text-text-secondary hover:text-text-primary"
                            >
                              Cancel
                            </button>
                            <button
                              onClick={() => handleReject(d.id)}
                              disabled={isLoading || !rejectReason.trim()}
                              className="rounded-md bg-status-red px-2.5 py-1 text-xs font-medium text-surface-primary hover:bg-status-red/90 disabled:opacity-50"
                            >
                              Confirm Reject
                            </button>
                          </div>
                        </div>
                      ) : (
                        <div
                          className="flex justify-end gap-1.5"
                          onClick={(e) => e.stopPropagation()}
                        >
                          <button
                            onClick={() => handleAccept(d.id)}
                            disabled={isLoading}
                            className="rounded-md bg-status-green px-2.5 py-1 text-xs font-medium text-surface-primary hover:bg-status-green/90 disabled:opacity-50"
                          >
                            Accept
                          </button>
                          <button
                            onClick={() => setRejectingId(d.id)}
                            disabled={isLoading}
                            className="rounded-md bg-status-red/15 px-2.5 py-1 text-xs font-medium text-status-red hover:bg-status-red/25 disabled:opacity-50"
                          >
                            Reject
                          </button>
                        </div>
                      )}
                    </td>
                  </tr>

                  {/* Expanded detail row */}
                  {isExpanded && (
                    <tr className="border-b border-border-subtle">
                      <td colSpan={8} className="bg-surface-overlay px-8 py-5">
                        <ReasoningCard
                          reasoning={d.reasoning}
                          sources={d.sources || []}
                        />
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
