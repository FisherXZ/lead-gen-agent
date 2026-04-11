// frontend/src/components/briefing/NeedsReviewPanel.tsx
"use client";

import { useState } from "react";
import Link from "next/link";
import { agentFetch } from "@/lib/agent-fetch";

export interface PendingDiscovery {
  id: string;
  epc_contractor: string;
  confidence: string;
  reasoning_summary: string;
  project_id: string;
  project_name: string;
  mw_capacity: number | null;
  iso_region: string;
}

interface NeedsReviewPanelProps {
  discoveries: PendingDiscovery[];
  totalPending: number;
  onCountChange?: (delta: number) => void;
}

const CONFIDENCE_STYLES: Record<string, string> = {
  confirmed: "badge-green",
  likely: "badge-amber",
  possible: "badge-neutral",
};

export default function NeedsReviewPanel({
  discoveries: initialDiscoveries,
  totalPending,
  onCountChange,
}: NeedsReviewPanelProps) {
  const [discoveries, setDiscoveries] =
    useState<PendingDiscovery[]>(initialDiscoveries);
  const [loadingId, setLoadingId] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const remaining = totalPending - (initialDiscoveries.length - discoveries.length);

  async function handleAction(id: string, action: "accepted" | "rejected") {
    setLoadingId(id);
    setError(null);
    try {
      const res = await agentFetch(`/api/discover/${id}/review`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action }),
      });
      if (res.ok) {
        setDiscoveries((prev) => prev.filter((d) => d.id !== id));
        onCountChange?.(-1);
      } else {
        setError(`Failed to ${action === "accepted" ? "approve" : "reject"}. Try again.`);
      }
    } catch {
      setError(`Failed to ${action === "accepted" ? "approve" : "reject"}. Try again.`);
    } finally {
      setLoadingId(null);
    }
  }

  return (
    <div className="rounded-lg border border-border-subtle bg-surface-raised">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-border-subtle px-4 py-3">
        <div className="flex items-center gap-2">
          <h2 className="text-[10px] font-medium uppercase tracking-widest text-text-tertiary">
            Needs Review
          </h2>
          {remaining > 0 && (
            <span className="rounded-full bg-accent-amber-muted px-2 py-0.5 text-[10px] font-semibold text-accent-amber">
              {remaining}
            </span>
          )}
        </div>
        <Link
          href="/review"
          className="text-[10px] text-text-tertiary transition-colors hover:text-text-secondary"
        >
          View all {remaining} →
        </Link>
      </div>

      {/* Error */}
      {error && (
        <div className="border-b border-border-subtle px-4 py-2">
          <p className="text-xs text-status-red">{error}</p>
        </div>
      )}

      {/* Cards */}
      <div className="divide-y divide-border-subtle">
        {discoveries.length === 0 ? (
          <div className="px-4 py-8 text-center">
            <p className="text-xs text-text-tertiary">
              All caught up. No pending reviews.
            </p>
          </div>
        ) : (
          discoveries.map((d) => {
            const isExpanded = expandedId === d.id;
            const isLoading = loadingId === d.id;
            const badgeStyle =
              CONFIDENCE_STYLES[d.confidence] || "badge-neutral";

            return (
              <div key={d.id} className="group">
                <div
                  role="button"
                  tabIndex={0}
                  onClick={() =>
                    setExpandedId(isExpanded ? null : d.id)
                  }
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      setExpandedId(isExpanded ? null : d.id);
                    }
                  }}
                  className="flex items-start justify-between px-4 py-3 transition-colors hover:bg-surface-overlay cursor-pointer"
                >
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="font-serif text-[13px] text-text-primary">
                        {d.epc_contractor}
                      </span>
                      <span
                        className={`rounded-full px-2 py-0.5 text-[10px] font-semibold capitalize ${badgeStyle}`}
                      >
                        {d.confidence}
                      </span>
                    </div>
                    <p className="mt-0.5 text-[10px] text-text-tertiary">
                      {d.project_name} · {d.mw_capacity ?? "—"}MW ·{" "}
                      {d.iso_region}
                    </p>
                  </div>

                  {/* Approve / Reject buttons */}
                  <div
                    className="ml-3 flex shrink-0 items-center gap-1.5"
                    onClick={(e) => e.stopPropagation()}
                  >
                    <button
                      onClick={() => handleAction(d.id, "accepted")}
                      disabled={isLoading}
                      aria-label={`Approve ${d.epc_contractor}`}
                      className="rounded-md bg-status-green/15 px-2 py-1 text-xs font-medium text-status-green transition-colors hover:bg-status-green/25 disabled:opacity-50"
                    >
                      ✓
                    </button>
                    <button
                      onClick={() => handleAction(d.id, "rejected")}
                      disabled={isLoading}
                      aria-label={`Reject ${d.epc_contractor}`}
                      className="rounded-md bg-status-red/15 px-2 py-1 text-xs font-medium text-status-red transition-colors hover:bg-status-red/25 disabled:opacity-50"
                    >
                      ✕
                    </button>
                  </div>
                </div>

                {/* Expanded reasoning */}
                {isExpanded && d.reasoning_summary && (
                  <div className="border-t border-border-subtle bg-surface-overlay px-4 py-3">
                    <p className="text-xs leading-relaxed text-text-secondary">
                      {d.reasoning_summary}
                    </p>
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>

      {/* Footer: + N more */}
      {remaining > discoveries.length && discoveries.length > 0 && (
        <div className="border-t border-border-subtle px-4 py-2 text-center">
          <Link
            href="/review"
            className="text-[10px] text-text-tertiary transition-colors hover:text-text-secondary"
          >
            + {remaining - discoveries.length} more →
          </Link>
        </div>
      )}
    </div>
  );
}
