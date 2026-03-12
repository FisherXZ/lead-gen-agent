"use client";

import ConfidenceBadge from "@/components/epc/ConfidenceBadge";

interface ProjectRow {
  id: string;
  project_name: string | null;
  developer: string | null;
  mw_capacity: number | null;
  state: string | null;
  iso_region: string;
  epc_company: string | null;
  fuel_type: string | null;
}

interface ProjectListCardProps {
  data: {
    projects?: ProjectRow[];
    count?: number;
  };
}

const AGENT_API_URL =
  process.env.NEXT_PUBLIC_AGENT_API_URL || "http://localhost:8000";

export default function ProjectListCard({ data }: ProjectListCardProps) {
  const projects = (data.projects || []) as ProjectRow[];

  if (projects.length === 0) {
    return (
      <div className="rounded-lg p-4 text-sm text-slate-500">
        No projects found matching your criteria.
      </div>
    );
  }

  return (
    <div className="overflow-hidden bg-white">
      <div className="border-b border-slate-100 bg-slate-50 px-4 py-2">
        <span className="text-xs font-medium text-slate-500">
          {data.count ?? projects.length} project{projects.length !== 1 ? "s" : ""} found
        </span>
      </div>
      <div className="divide-y divide-slate-100">
        {projects.map((p) => (
          <div
            key={p.id}
            className="flex items-center justify-between px-4 py-3"
          >
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <span className="truncate text-sm font-medium text-slate-900">
                  {p.project_name || p.id}
                </span>
                {p.mw_capacity && (
                  <span className="shrink-0 text-xs text-slate-400">
                    {p.mw_capacity} MW
                  </span>
                )}
              </div>
              <div className="mt-0.5 flex items-center gap-2 text-xs text-slate-500">
                {p.developer && <span>{p.developer}</span>}
                {p.state && <span>&middot; {p.state}</span>}
                {p.iso_region && <span>&middot; {p.iso_region}</span>}
                {p.fuel_type && <span>&middot; {p.fuel_type}</span>}
              </div>
            </div>
            <div className="ml-3 shrink-0">
              {p.epc_company ? (
                <span className="text-xs text-emerald-600">{p.epc_company}</span>
              ) : (
                <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-400">
                  No EPC
                </span>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
