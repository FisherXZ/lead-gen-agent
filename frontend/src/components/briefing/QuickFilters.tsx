"use client";

import { BriefingFilters, BriefingRegionFilter, BriefingTimeFilter } from "@/lib/briefing-types";

interface QuickFiltersProps {
  filters: BriefingFilters;
  onChange: (filters: BriefingFilters) => void;
}

const REGIONS: { value: BriefingRegionFilter; label: string }[] = [
  { value: "all", label: "All Regions" },
  { value: "ERCOT", label: "ERCOT" },
  { value: "CAISO", label: "CAISO" },
  { value: "MISO", label: "MISO" },
];

const TIME_RANGES: { value: BriefingTimeFilter; label: string }[] = [
  { value: "today", label: "Today" },
  { value: "this_week", label: "This Week" },
  { value: "this_month", label: "This Month" },
];

export function QuickFilters({ filters, onChange }: QuickFiltersProps) {
  return (
    <div className="flex items-center gap-2">
      {REGIONS.map((r) => (
        <button
          key={r.value}
          onClick={() => onChange({ ...filters, region: r.value })}
          className={`px-3 py-1.5 rounded-full text-xs font-sans font-medium transition-colors ${
            filters.region === r.value
              ? "bg-accent-amber-muted text-accent-amber"
              : "bg-surface-overlay text-text-secondary hover:text-text-primary"
          }`}
        >
          {r.label}
        </button>
      ))}
      <div className="w-px h-4 bg-border-subtle mx-1" />
      {TIME_RANGES.map((t) => (
        <button
          key={t.value}
          onClick={() => onChange({ ...filters, timeRange: t.value })}
          className={`px-3 py-1.5 rounded-full text-xs font-sans font-medium transition-colors ${
            filters.timeRange === t.value
              ? "bg-accent-amber-muted text-accent-amber"
              : "bg-surface-overlay text-text-secondary hover:text-text-primary"
          }`}
        >
          {t.label}
        </button>
      ))}
    </div>
  );
}
