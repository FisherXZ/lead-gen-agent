"use client";

import type { ReactNode } from "react";

interface TimelineStage {
  name: string;
  status: "pending" | "active" | "complete" | "error";
  children: ReactNode[];
}

interface ResearchTimelineProps {
  stages: TimelineStage[];
}

function StageDot({ status }: { status: TimelineStage["status"] }) {
  if (status === "complete") {
    return (
      <svg
        width={14}
        height={14}
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth={2.5}
        strokeLinecap="round"
        strokeLinejoin="round"
        className="shrink-0 text-status-green"
      >
        <polyline points="20 6 9 17 4 12" />
      </svg>
    );
  }
  if (status === "error") {
    return (
      <svg
        width={14}
        height={14}
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth={2.5}
        strokeLinecap="round"
        strokeLinejoin="round"
        className="shrink-0 text-status-red"
      >
        <line x1="18" y1="6" x2="6" y2="18" />
        <line x1="6" y1="6" x2="18" y2="18" />
      </svg>
    );
  }
  if (status === "active") {
    return (
      <span className="flex h-3.5 w-3.5 items-center justify-center shrink-0">
        <span className="h-2 w-2 rounded-full bg-accent-amber animate-timeline-pulse" />
      </span>
    );
  }
  // pending
  return (
    <span className="flex h-3.5 w-3.5 items-center justify-center shrink-0">
      <span className="h-2 w-2 rounded-full border border-border-default bg-transparent" />
    </span>
  );
}

function formatStageName(name: string): string {
  return name
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

export default function ResearchTimeline({ stages }: ResearchTimelineProps) {
  return (
    <div role="list" aria-label="Research progress" className="relative">
      {stages.map((stage, si) => {
        const isLast = si === stages.length - 1;
        return (
          <div key={si} role="listitem" className="relative flex gap-3">
            {/* Connector line + dot column */}
            <div className="flex flex-col items-center">
              <div
                className="flex h-5 w-3.5 items-center justify-center"
                aria-label={`${formatStageName(stage.name)}, ${stage.status}`}
              >
                <StageDot status={stage.status} />
              </div>
              {/* Vertical connector */}
              {!isLast && (
                <div className="w-px flex-1 bg-border-subtle" />
              )}
            </div>

            {/* Content column */}
            <div className={`flex-1 min-w-0 ${isLast ? "pb-0" : "pb-4"}`}>
              {/* Stage header */}
              <div className="flex items-center gap-2 h-5">
                <span className="text-[11px] font-medium tracking-[0.08em] uppercase text-text-tertiary">
                  {formatStageName(stage.name)}
                </span>
                {stage.children.length > 0 && stage.status === "complete" && (
                  <span className="text-[11px] text-text-tertiary">
                    ({stage.children.length} {stage.children.length === 1 ? "source" : "sources"})
                  </span>
                )}
              </div>

              {/* Child tool cards */}
              {stage.children.length > 0 && (
                <div className="mt-2 flex flex-col gap-2">
                  {stage.children.map((child, ci) => (
                    <div key={ci} className="animate-fade-slide-in">
                      {child}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
