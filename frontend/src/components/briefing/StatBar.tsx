"use client";

import { BriefingStats } from "@/lib/briefing-types";

interface StatBarProps {
  stats: BriefingStats;
}

export function StatBar({ stats }: StatBarProps) {
  return (
    <div className="flex items-center gap-3 text-sm font-sans text-[--text-secondary]">
      <span>
        <strong className="text-[--text-primary] font-medium">
          {stats.new_leads_this_week}
        </strong>{" "}
        new leads this week
      </span>
      <span className="text-[--border-default]">·</span>
      <span>
        <strong className="text-[--accent-amber] font-medium">
          {stats.awaiting_review}
        </strong>{" "}
        awaiting review
      </span>
      <span className="text-[--border-default]">·</span>
      <span>
        <strong className="text-[--text-primary] font-medium">
          {stats.total_epcs_discovered}
        </strong>{" "}
        EPCs discovered
      </span>
    </div>
  );
}
