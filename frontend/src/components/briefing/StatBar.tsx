"use client";

import { BriefingStats } from "@/lib/briefing-types";

interface StatBarProps {
  stats: BriefingStats;
}

export function StatBar({ stats }: StatBarProps) {
  return (
    <div className="flex items-baseline gap-6 pb-6 border-b border-[--border-subtle]">
      <div>
        <span className="text-2xl font-serif text-[--text-primary]">
          {stats.new_leads_this_week}
        </span>
        <span className="ml-2 text-sm text-[--text-secondary]">
          new leads this week
        </span>
      </div>
      <div>
        <span className="text-2xl font-serif text-[--accent-amber]">
          {stats.awaiting_review}
        </span>
        <span className="ml-2 text-sm text-[--text-secondary]">
          awaiting review
        </span>
      </div>
      <div>
        <span className="text-2xl font-serif text-[--text-primary]">
          {stats.total_epcs_discovered}
        </span>
        <span className="ml-2 text-sm text-[--text-secondary]">
          EPCs discovered
        </span>
      </div>
    </div>
  );
}
