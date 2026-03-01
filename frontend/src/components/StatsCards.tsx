"use client";

import { Project, ScrapeRun } from "@/lib/types";

interface StatsCardsProps {
  projects: Project[];
  lastRuns: ScrapeRun[];
}

export default function StatsCards({ projects, lastRuns }: StatsCardsProps) {
  const totalProjects = projects.length;
  const totalGW = (
    projects.reduce((sum, p) => sum + (p.mw_capacity || 0), 0) / 1000
  ).toFixed(1);

  const byCounts: Record<string, number> = {};
  for (const p of projects) {
    byCounts[p.iso_region] = (byCounts[p.iso_region] || 0) + 1;
  }

  const lastUpdated = lastRuns.length
    ? new Date(
        Math.max(...lastRuns.map((r) => new Date(r.completed_at || r.started_at).getTime()))
      )
    : null;

  const cards = [
    {
      label: "Total Projects",
      value: totalProjects.toLocaleString(),
    },
    {
      label: "Total Capacity",
      value: `${totalGW} GW`,
    },
    {
      label: "By ISO",
      value: ["MISO", "ERCOT", "CAISO"]
        .filter((iso) => byCounts[iso])
        .map((iso) => `${iso}: ${byCounts[iso]?.toLocaleString()}`)
        .join(" / "),
    },
    {
      label: "Last Updated",
      value: lastUpdated
        ? lastUpdated.toLocaleDateString("en-US", {
            month: "short",
            day: "numeric",
            year: "numeric",
            hour: "numeric",
            minute: "2-digit",
          })
        : "Never",
    },
  ];

  return (
    <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
      {cards.map((card) => (
        <div
          key={card.label}
          className="rounded-lg border border-slate-200 bg-white p-5"
        >
          <p className="text-sm font-medium text-slate-500">{card.label}</p>
          <p className="mt-1 text-lg font-semibold text-slate-900">
            {card.value}
          </p>
        </div>
      ))}
    </div>
  );
}
