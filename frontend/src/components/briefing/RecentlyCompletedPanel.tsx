// frontend/src/components/briefing/RecentlyCompletedPanel.tsx
"use client";

import Link from "next/link";

export interface CompletedItem {
  discovery_id: string;
  project_id: string;
  epc_contractor: string;
  project_name: string;
  mw_capacity: number | null;
  contact_count: number;
  has_hubspot_sync: boolean;
  completed_at: string;
}

interface RecentlyCompletedPanelProps {
  items: CompletedItem[];
}

function timeAgo(dateStr: string): string {
  const now = new Date();
  const date = new Date(dateStr);
  const diffMs = now.getTime() - date.getTime();
  const diffMin = Math.floor(diffMs / 60000);
  if (diffMin < 1) return "just now";
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHrs = Math.floor(diffMin / 60);
  if (diffHrs < 24) return `${diffHrs}h ago`;
  const diffDays = Math.floor(diffHrs / 24);
  if (diffDays < 7) return `${diffDays}d ago`;
  return date.toLocaleDateString();
}

export default function RecentlyCompletedPanel({
  items,
}: RecentlyCompletedPanelProps) {
  return (
    <div className="rounded-lg border border-border-subtle bg-surface-raised">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-border-subtle px-4 py-3">
        <div className="flex items-center gap-2">
          <h2 className="text-[10px] font-medium uppercase tracking-widest text-text-tertiary">
            Recently Completed
          </h2>
          {items.length > 0 && (
            <span className="rounded-full bg-status-green/15 px-2 py-0.5 text-[10px] font-semibold text-status-green">
              {items.length}
            </span>
          )}
        </div>
      </div>

      {/* Cards */}
      <div className="divide-y divide-border-subtle">
        {items.length === 0 ? (
          <div className="px-4 py-8 text-center">
            <p className="text-xs text-text-tertiary">
              No completed actions yet.
            </p>
          </div>
        ) : (
          items.map((item) => (
            <Link
              key={item.discovery_id}
              href={`/projects/${item.project_id}`}
              className="flex items-start gap-3 px-4 py-3 transition-colors"
            >
              {/* Green dot */}
              <span
                className="mt-1.5 inline-block h-1.5 w-1.5 shrink-0 rounded-full bg-status-green"
                aria-hidden="true"
              />

              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="font-serif text-[13px] text-text-primary">
                    {item.epc_contractor}
                  </span>
                  {item.has_hubspot_sync ? (
                    <span className="rounded-full bg-status-green/15 px-2 py-0.5 text-[10px] font-semibold text-status-green">
                      In HubSpot
                    </span>
                  ) : (
                    <span className="rounded-full bg-status-green/10 px-2 py-0.5 text-[10px] font-medium text-status-green/70">
                      Accepted
                    </span>
                  )}
                </div>
                <p className="mt-0.5 text-[10px] text-text-tertiary">
                  {item.project_name}
                  {item.mw_capacity ? ` · ${item.mw_capacity}MW` : ""}
                  {item.contact_count > 0
                    ? ` · ${item.contact_count} contacts`
                    : ""}
                  {" · "}
                  {timeAgo(item.completed_at)}
                </p>
              </div>
            </Link>
          ))
        )}
      </div>
    </div>
  );
}
