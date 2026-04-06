// frontend/src/components/briefing/PipelineFunnel.tsx
"use client";

import Link from "next/link";

interface FunnelStage {
  label: string;
  count: number;
  href: string;
}

interface PipelineFunnelProps {
  totalProjects: number;
  researched: number;
  pendingReview: number;
  accepted: number;
  inCrm: number;
}

export default function PipelineFunnel({
  totalProjects,
  researched,
  pendingReview,
  accepted,
  inCrm,
}: PipelineFunnelProps) {
  const stages: FunnelStage[] = [
    { label: "Projects", count: totalProjects, href: "/projects" },
    { label: "Researched", count: researched, href: "/projects" },
    { label: "Pending Review", count: pendingReview, href: "/review" },
    { label: "Accepted", count: accepted, href: "/actions" },
    { label: "In CRM", count: inCrm, href: "/actions" },
  ];

  return (
    <div className="rounded-lg border border-border-subtle bg-surface-raised px-4 py-4">
      {/* Desktop: horizontal row */}
      <div className="hidden sm:flex items-center justify-between">
        {stages.map((stage, i) => {
          const isPendingReview = i === 2;
          const isBottleneck = isPendingReview && stage.count > 0;

          return (
            <div key={stage.label} className="flex items-center">
              <Link
                href={stage.href}
                className={`group flex flex-col items-center rounded-md px-4 py-2 transition-colors hover:bg-surface-overlay ${
                  isBottleneck
                    ? "bg-accent-amber-muted border border-accent-amber-muted"
                    : ""
                }`}
              >
                <span
                  className={`font-serif text-[26px] leading-tight ${
                    isBottleneck
                      ? "text-accent-amber"
                      : stage.count === 0 && i === 4
                        ? "text-text-tertiary"
                        : i === 3
                          ? "text-status-green"
                          : "text-text-primary"
                  }`}
                >
                  {stage.count}
                </span>
                <span
                  className={`mt-0.5 text-[9px] font-medium uppercase tracking-widest ${
                    isBottleneck ? "text-accent-amber" : "text-text-tertiary"
                  }`}
                >
                  {stage.label}
                </span>
              </Link>
              {i < stages.length - 1 && (
                <span className="mx-2 text-text-tertiary" aria-hidden="true">
                  →
                </span>
              )}
            </div>
          );
        })}
      </div>

      {/* Mobile: vertical list */}
      <div className="flex flex-col gap-2 sm:hidden">
        {stages.map((stage, i) => {
          const isPendingReview = i === 2;
          const isBottleneck = isPendingReview && stage.count > 0;

          return (
            <Link
              key={stage.label}
              href={stage.href}
              className={`flex items-center justify-between rounded-md px-3 py-2 transition-colors hover:bg-surface-overlay ${
                isBottleneck
                  ? "bg-accent-amber-muted border border-accent-amber-muted"
                  : ""
              }`}
            >
              <span
                className={`text-[9px] font-medium uppercase tracking-widest ${
                  isBottleneck ? "text-accent-amber" : "text-text-tertiary"
                }`}
              >
                {stage.label}
              </span>
              <span
                className={`font-serif text-lg leading-tight ${
                  isBottleneck
                    ? "text-accent-amber"
                    : stage.count === 0 && i === 4
                      ? "text-text-tertiary"
                      : i === 3
                        ? "text-status-green"
                        : "text-text-primary"
                }`}
              >
                {stage.count}
              </span>
            </Link>
          );
        })}
      </div>
    </div>
  );
}
