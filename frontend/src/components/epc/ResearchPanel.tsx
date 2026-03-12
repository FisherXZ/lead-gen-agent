"use client";

import { Project, EpcDiscovery } from "@/lib/types";
import ConfidenceBadge from "./ConfidenceBadge";
import ReasoningCard from "./ReasoningCard";

interface ResearchPanelProps {
  project: Project | null;
  discovery: EpcDiscovery | null | undefined;
  onReview: (discoveryId: string, action: "accepted" | "rejected") => void;
}

export default function ResearchPanel({
  project,
  discovery,
  onReview,
}: ResearchPanelProps) {
  if (!project) {
    return (
      <div className="flex h-full items-center justify-center rounded-lg border border-slate-200 bg-white p-8">
        <p className="text-sm text-slate-400">
          Select a project to view research results
        </p>
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-slate-200 bg-white">
      {/* Project header */}
      <div className="border-b border-slate-200 p-5">
        <h3 className="text-lg font-semibold text-slate-900">
          {project.project_name || project.queue_id}
        </h3>
        <div className="mt-1 flex flex-wrap gap-3 text-sm text-slate-500">
          {project.developer && <span>{project.developer}</span>}
          {project.mw_capacity && <span>{project.mw_capacity} MW</span>}
          {project.state && <span>{project.state}</span>}
          <span>{project.iso_region}</span>
        </div>
      </div>

      {/* Discovery content */}
      <div className="p-5">
        {!discovery ? (
          <div className="py-8 text-center">
            <p className="text-sm text-slate-400">
              No research results yet. Click Research to start.
            </p>
          </div>
        ) : (
          <div className="flex flex-col gap-5">
            {/* EPC contractor name and confidence */}
            <div>
              <p className="text-xs font-medium uppercase tracking-wider text-slate-400">
                EPC Contractor
              </p>
              <div className="mt-1 flex items-center gap-3">
                <span className="text-xl font-bold text-slate-900">
                  {discovery.epc_contractor}
                </span>
                <ConfidenceBadge confidence={discovery.confidence} />
              </div>
            </div>

            <ReasoningCard
              reasoning={discovery.reasoning}
              sources={discovery.sources}
            />

            {/* Review actions */}
            <div className="border-t border-slate-200 pt-4">
              {discovery.review_status === "pending" ? (
                <div className="flex items-center gap-3">
                  <span className="text-sm text-slate-500">Review:</span>
                  <button
                    onClick={() => onReview(discovery.id, "accepted")}
                    className="rounded-md bg-emerald-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-emerald-700"
                  >
                    Accept
                  </button>
                  <button
                    onClick={() => onReview(discovery.id, "rejected")}
                    className="rounded-md border border-slate-300 px-4 py-2 text-sm font-medium text-slate-600 transition-colors hover:bg-slate-50"
                  >
                    Reject
                  </button>
                </div>
              ) : (
                <div className="flex items-center gap-2">
                  <span className="text-sm text-slate-500">Status:</span>
                  <span
                    className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-semibold capitalize ${
                      discovery.review_status === "accepted"
                        ? "bg-emerald-100 text-emerald-700"
                        : "bg-red-100 text-red-700"
                    }`}
                  >
                    {discovery.review_status}
                  </span>
                </div>
              )}
            </div>

            {/* Token usage */}
            {discovery.tokens_used > 0 && (
              <p className="text-xs text-slate-400">
                Tokens used: {discovery.tokens_used.toLocaleString()}
              </p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
