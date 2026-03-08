"use client";

import Link from "next/link";
import { Project } from "@/lib/types";

import { ConstructionStatus } from "@/lib/types";

type SortField =
  | "lead_score"
  | "project_name"
  | "developer"
  | "iso_region"
  | "state"
  | "mw_capacity"
  | "fuel_type"
  | "status"
  | "construction_status"
  | "queue_date"
  | "expected_cod";

interface ProjectsTableProps {
  projects: Project[];
  sortField: SortField;
  sortDir: "asc" | "desc";
  onSort: (field: SortField) => void;
  page: number;
  pageSize: number;
  onPageChange: (page: number) => void;
}

function ScoreBadge({ score }: { score: number }) {
  let bg = "bg-red-100 text-red-700";
  if (score >= 70) bg = "bg-emerald-100 text-emerald-700";
  else if (score >= 40) bg = "bg-amber-100 text-amber-700";

  return (
    <span className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-semibold ${bg}`}>
      {score}
    </span>
  );
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

const COLUMNS: { key: SortField; label: string; align?: "right" }[] = [
  { key: "lead_score", label: "Score" },
  { key: "project_name", label: "Project" },
  { key: "developer", label: "Developer" },
  { key: "iso_region", label: "ISO" },
  { key: "state", label: "State" },
  { key: "mw_capacity", label: "MW", align: "right" },
  { key: "fuel_type", label: "Type" },
  { key: "status", label: "Queue Status" },
  { key: "construction_status", label: "Construction" },
  { key: "queue_date", label: "Queue Date" },
  { key: "expected_cod", label: "Expected COD" },
];

export type { SortField };

export default function ProjectsTable({
  projects,
  sortField,
  sortDir,
  onSort,
  page,
  pageSize,
  onPageChange,
}: ProjectsTableProps) {
  const totalPages = Math.max(1, Math.ceil(projects.length / pageSize));
  const start = page * pageSize;
  const pageProjects = projects.slice(start, start + pageSize);

  return (
    <div className="overflow-hidden rounded-lg border border-slate-200 bg-white">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-200 bg-slate-50">
              {COLUMNS.map((col) => (
                <th
                  key={col.key}
                  className={`cursor-pointer whitespace-nowrap px-4 py-3 text-left font-medium text-slate-600 select-none hover:text-slate-900 ${col.align === "right" ? "text-right" : ""}`}
                  onClick={() => onSort(col.key)}
                >
                  {col.label}
                  {sortField === col.key && (
                    <span className="ml-1">{sortDir === "asc" ? "\u2191" : "\u2193"}</span>
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
                  className="px-4 py-12 text-center text-slate-400"
                >
                  No projects match your filters.
                </td>
              </tr>
            ) : (
              pageProjects.map((p) => (
                <tr
                  key={p.id}
                  className="border-b border-slate-100 transition-colors hover:bg-slate-50"
                >
                  <td className="px-4 py-3">
                    <ScoreBadge score={p.lead_score} />
                  </td>
                  <td className="max-w-[200px] truncate px-4 py-3 font-medium text-slate-900">
                    <Link
                      href={`/projects/${p.id}`}
                      className="hover:text-blue-600 hover:underline"
                    >
                      {p.project_name || "—"}
                    </Link>
                  </td>
                  <td className="max-w-[180px] truncate px-4 py-3 text-slate-600">
                    {p.developer || "—"}
                  </td>
                  <td className="px-4 py-3 text-slate-600">{p.iso_region}</td>
                  <td className="px-4 py-3 text-slate-600">{p.state || "—"}</td>
                  <td className="px-4 py-3 text-right tabular-nums text-slate-900">
                    {p.mw_capacity?.toLocaleString() || "—"}
                  </td>
                  <td className="px-4 py-3 text-slate-600">{p.fuel_type || "—"}</td>
                  <td className="px-4 py-3">
                    <StatusPill status={p.status} />
                  </td>
                  <td className="px-4 py-3">
                    <ConstructionPill status={p.construction_status} />
                  </td>
                  <td className="whitespace-nowrap px-4 py-3 text-slate-500">
                    {formatDate(p.queue_date)}
                  </td>
                  <td className="whitespace-nowrap px-4 py-3 text-slate-500">
                    {formatDate(p.expected_cod)}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      <div className="flex items-center justify-between border-t border-slate-200 px-4 py-3">
        <p className="text-sm text-slate-500">
          {projects.length > 0
            ? `Showing ${start + 1}–${Math.min(start + pageSize, projects.length)} of ${projects.length.toLocaleString()}`
            : "0 results"}
        </p>
        <div className="flex gap-2">
          <button
            className="rounded-md border border-slate-200 px-3 py-1.5 text-sm text-slate-600 transition-colors hover:bg-slate-50 disabled:opacity-40"
            onClick={() => onPageChange(page - 1)}
            disabled={page === 0}
          >
            Previous
          </button>
          <button
            className="rounded-md border border-slate-200 px-3 py-1.5 text-sm text-slate-600 transition-colors hover:bg-slate-50 disabled:opacity-40"
            onClick={() => onPageChange(page + 1)}
            disabled={page >= totalPages - 1}
          >
            Next
          </button>
        </div>
      </div>
    </div>
  );
}

const CONSTRUCTION_LABELS: Record<string, string> = {
  unknown: "Unknown",
  pre_construction: "Pre-Construction",
  under_construction: "Under Construction",
  completed: "Completed",
  cancelled: "Cancelled",
};

function ConstructionPill({ status }: { status: ConstructionStatus }) {
  const cls: Record<string, string> = {
    pre_construction: "bg-amber-50 text-amber-700",
    under_construction: "bg-blue-50 text-blue-700",
    completed: "bg-emerald-50 text-emerald-700",
    cancelled: "bg-red-50 text-red-600",
    unknown: "bg-slate-100 text-slate-500",
  };
  return (
    <span
      className={`inline-block whitespace-nowrap rounded-full px-2.5 py-0.5 text-xs font-medium ${cls[status] || cls.unknown}`}
    >
      {CONSTRUCTION_LABELS[status] || "Unknown"}
    </span>
  );
}

function StatusPill({ status }: { status: string | null }) {
  const s = (status || "").toLowerCase();
  let cls = "bg-slate-100 text-slate-600";
  if (s.includes("active")) cls = "bg-emerald-50 text-emerald-700";
  else if (s.includes("completed") || s.includes("done"))
    cls = "bg-blue-50 text-blue-700";
  else if (s.includes("withdrawn")) cls = "bg-red-50 text-red-600";

  return (
    <span className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-medium ${cls}`}>
      {status || "—"}
    </span>
  );
}
