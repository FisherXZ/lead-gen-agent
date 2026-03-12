"use client";

import ConfidenceBadge from "@/components/epc/ConfidenceBadge";

interface DiscoveryRow {
  id: string;
  project_id: string;
  epc_contractor: string;
  confidence: string;
  review_status: string;
}

interface DiscoveryListCardProps {
  data: {
    discoveries?: DiscoveryRow[];
    count?: number;
  };
}

const STATUS_STYLES: Record<string, string> = {
  accepted: "bg-emerald-100 text-emerald-700",
  rejected: "bg-red-100 text-red-700",
  pending: "bg-amber-100 text-amber-700",
};

export default function DiscoveryListCard({ data }: DiscoveryListCardProps) {
  const discoveries = data.discoveries || [];

  if (discoveries.length === 0) {
    return (
      <div className="rounded-lg p-4 text-sm text-slate-500">
        No discoveries found.
      </div>
    );
  }

  return (
    <div className="overflow-hidden bg-white">
      <div className="border-b border-slate-100 bg-slate-50 px-4 py-2">
        <span className="text-xs font-medium text-slate-500">
          {data.count ?? discoveries.length} discover{discoveries.length !== 1 ? "ies" : "y"}
        </span>
      </div>
      <div className="divide-y divide-slate-100">
        {discoveries.map((d) => (
          <div
            key={d.id}
            className="flex items-center justify-between px-4 py-3"
          >
            <div className="flex items-center gap-2">
              <span className="text-sm font-medium text-slate-900">
                {d.epc_contractor}
              </span>
              <ConfidenceBadge confidence={d.confidence} />
            </div>
            <span
              className={`rounded-full px-2 py-0.5 text-xs font-medium capitalize ${
                STATUS_STYLES[d.review_status] || STATUS_STYLES.pending
              }`}
            >
              {d.review_status}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
