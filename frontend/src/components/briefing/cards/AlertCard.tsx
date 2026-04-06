"use client";

import { useState } from "react";
import { NewProjectEvent, StatusChangeEvent } from "@/lib/briefing-types";
import { agentFetch } from "@/lib/agent-fetch";
import { toast } from "sonner";

type AlertEvent = NewProjectEvent | StatusChangeEvent;

interface AlertCardProps {
  event: AlertEvent;
  onExpand: (projectId: string) => void;
  onDismiss: (eventId: string) => void;
}

const STATUS_LABELS: Record<string, string> = {
  unknown: "Unknown",
  pre_construction: "Pre-Construction",
  under_construction: "Under Construction",
  completed: "Completed",
  cancelled: "Cancelled",
};

export function AlertCard({ event, onExpand, onDismiss }: AlertCardProps) {
  const [researching, setResearching] = useState(false);

  async function handleResearchEpc() {
    setResearching(true);
    try {
      const planRes = await agentFetch("/api/discover/plan", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ project_id: event.project_id }),
      });
      if (!planRes.ok) throw new Error("Plan failed");
      const { plan } = await planRes.json();

      const execRes = await agentFetch("/api/discover", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ project_id: event.project_id, plan }),
      });
      if (!execRes.ok) throw new Error("Research failed");
      toast.success("EPC research started");
    } catch {
      toast.error("Failed to start research");
    } finally {
      setResearching(false);
    }
  }

  if (event.type === "new_project") {
    return (
      <div className="bg-surface-raised rounded-lg p-4">
        <div className="flex items-start justify-between">
          <div>
            <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-sans font-medium uppercase tracking-wider bg-surface-overlay text-text-tertiary mb-1">
              New Project
            </span>
            <h3 className="font-serif text-base text-text-primary">
              {event.project_name}
            </h3>
            <p className="text-sm text-text-secondary">
              {event.developer && `${event.developer} · `}
              {event.mw_capacity && `${event.mw_capacity} MW · `}
              {event.iso_region}
              {event.state && ` · ${event.state}`}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={handleResearchEpc}
              disabled={researching}
              className="px-3 py-1.5 text-xs font-sans font-medium rounded bg-accent-amber-muted text-accent-amber hover:bg-accent-amber/25 disabled:opacity-50 transition-colors"
            >
              {researching ? "Researching\u2026" : "Research EPC"}
            </button>
            <button
              onClick={() => onDismiss(event.id)}
              className="px-2 py-1.5 text-xs text-text-tertiary hover:text-text-secondary transition-colors"
            >
              Dismiss
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="bg-surface-raised rounded-lg p-4">
      <div className="flex items-start justify-between">
        <div>
          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-sans font-medium uppercase tracking-wider bg-surface-overlay text-text-tertiary mb-1">
            Status Change
          </span>
          <h3 className="font-serif text-base text-text-primary">
            {event.project_name}
          </h3>
          <p className="text-sm text-text-secondary">
            {STATUS_LABELS[event.previous_status] || event.previous_status}
            {" → "}
            <span className="text-text-primary font-medium">
              {STATUS_LABELS[event.new_status] || event.new_status}
            </span>
            {event.expected_cod && ` · COD: ${event.expected_cod}`}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => onExpand(event.project_id)}
            className="px-3 py-1.5 text-xs font-sans font-medium rounded bg-surface-overlay text-text-secondary hover:text-text-primary transition-colors"
          >
            Details
          </button>
          <button
            onClick={() => onDismiss(event.id)}
            className="px-2 py-1.5 text-xs text-text-tertiary hover:text-text-secondary transition-colors"
          >
            Dismiss
          </button>
        </div>
      </div>
    </div>
  );
}
