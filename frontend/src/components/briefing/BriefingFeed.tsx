"use client";

import { useState, useMemo } from "react";
import {
  AnyBriefingEvent,
  BriefingFilters,
  BriefingStats,
} from "@/lib/briefing-types";
import { StatBar } from "./StatBar";
import { QuickFilters } from "./QuickFilters";
import { NewLeadCard } from "./cards/NewLeadCard";
import { ReviewCard } from "./cards/ReviewCard";
import { AlertCard } from "./cards/AlertCard";
import { DigestCard } from "./cards/DigestCard";
import { ProjectPanel } from "./ProjectPanel";

interface BriefingFeedProps {
  events: AnyBriefingEvent[];
  stats: BriefingStats;
}

function getTimeRangeStart(range: BriefingFilters["timeRange"]): Date {
  const now = new Date();
  switch (range) {
    case "today":
      return new Date(now.getFullYear(), now.getMonth(), now.getDate());
    case "this_week": {
      const d = new Date(now);
      d.setDate(d.getDate() - d.getDay());
      d.setHours(0, 0, 0, 0);
      return d;
    }
    case "this_month":
      return new Date(now.getFullYear(), now.getMonth(), 1);
  }
}

export function BriefingFeed({ events: initialEvents, stats }: BriefingFeedProps) {
  const [filters, setFilters] = useState<BriefingFilters>({
    region: "all",
    timeRange: "this_week",
  });
  const [dismissedIds, setDismissedIds] = useState<Set<string>>(new Set());
  const [expandedProjectId, setExpandedProjectId] = useState<string | null>(null);
  const [showHistory, setShowHistory] = useState(false);

  const filteredEvents = useMemo(() => {
    const rangeStart = getTimeRangeStart(filters.timeRange);

    return initialEvents.filter((e) => {
      if (new Date(e.created_at) < rangeStart) return false;
      if (filters.region !== "all") {
        if ("iso_region" in e && (e as any).iso_region !== filters.region) return false;
      }
      return true;
    });
  }, [initialEvents, filters]);

  const activeEvents = filteredEvents.filter((e) => !dismissedIds.has(e.id));
  const dismissedEvents = filteredEvents.filter((e) => dismissedIds.has(e.id));

  const sortedActive = [...activeEvents].sort((a, b) => {
    if (a.priority !== b.priority) return a.priority - b.priority;
    return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
  });

  function handleDismiss(eventId: string) {
    setDismissedIds((prev) => new Set([...prev, eventId]));
  }

  function renderCard(event: AnyBriefingEvent) {
    switch (event.type) {
      case "new_lead":
        return (
          <NewLeadCard
            key={event.id}
            event={event}
            onExpand={setExpandedProjectId}
            onDismiss={handleDismiss}
          />
        );
      case "review":
        return (
          <ReviewCard
            key={event.id}
            event={event}
            onDismiss={handleDismiss}
          />
        );
      case "new_project":
      case "status_change":
        return (
          <AlertCard
            key={event.id}
            event={event}
            onExpand={setExpandedProjectId}
            onDismiss={handleDismiss}
          />
        );
      case "digest":
        return <DigestCard key={event.id} event={event} />;
    }
  }

  return (
    <div className="space-y-6">
      <StatBar stats={stats} />
      <QuickFilters filters={filters} onChange={setFilters} />

      <div className="space-y-3">
        {sortedActive.length === 0 ? (
          <div className="text-center py-20">
            <h3 className="font-serif text-2xl text-[--text-primary] mb-3">
              You&apos;re all caught up
            </h3>
            <p className="text-sm text-[--text-tertiary] mb-6">
              No new events for the selected filters. Try expanding the time range.
            </p>
            <a
              href="/agent"
              className="text-sm text-[--accent-amber] hover:underline"
            >
              Start investigating →
            </a>
          </div>
        ) : (
          sortedActive.map(renderCard)
        )}
      </div>

      {dismissedEvents.length > 0 && (
        <div className="pt-4 border-t border-[--border-subtle]">
          <button
            onClick={() => setShowHistory(!showHistory)}
            className="text-xs font-sans text-[--text-tertiary] hover:text-[--text-secondary] transition-colors"
          >
            {showHistory ? "Hide" : "Show"} dismissed ({dismissedEvents.length})
          </button>
          {showHistory && (
            <div className="mt-3 space-y-3 opacity-60">
              {dismissedEvents.map(renderCard)}
            </div>
          )}
        </div>
      )}

      <ProjectPanel
        projectId={expandedProjectId}
        onClose={() => setExpandedProjectId(null)}
      />
    </div>
  );
}
