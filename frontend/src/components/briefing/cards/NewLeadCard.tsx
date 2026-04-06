"use client";

import { useState } from "react";
import { NewLeadEvent } from "@/lib/briefing-types";
import { agentFetch } from "@/lib/agent-fetch";
import { toast } from "sonner";

interface NewLeadCardProps {
  event: NewLeadEvent;
  onExpand: (projectId: string) => void;
  onDismiss: (eventId: string) => void;
}

export function NewLeadCard({ event, onExpand, onDismiss }: NewLeadCardProps) {
  const [pushing, setPushing] = useState(false);
  const [copied, setCopied] = useState(false);

  async function handlePushToHubspot() {
    setPushing(true);
    try {
      const res = await agentFetch("/api/hubspot/push", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ project_id: event.project_id }),
      });
      if (!res.ok) throw new Error("Push failed");
      toast.success("Pushed to HubSpot");
    } catch {
      toast.error("Failed to push to HubSpot");
    } finally {
      setPushing(false);
    }
  }

  function handleCopyOutreach() {
    navigator.clipboard.writeText(event.outreach_context);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
    toast.success("Outreach copied to clipboard");
  }

  return (
    <div className="bg-surface-raised border border-border-subtle border-l-2 border-l-accent-amber rounded-lg p-5">
      <div className="flex items-start justify-between mb-3">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-sans font-medium uppercase tracking-wider bg-status-green/15 text-status-green">
              New Lead
            </span>
            <span className="text-xs font-mono text-text-tertiary">
              {event.iso_region}
            </span>
          </div>
          <h3 className="font-serif text-lg text-text-primary">
            {event.epc_contractor}
          </h3>
          <p className="text-sm text-text-secondary">
            {event.project_name}
            {event.mw_capacity && ` · ${event.mw_capacity} MW`}
            {event.state && ` · ${event.state}`}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span
            className={`text-sm font-mono font-medium ${
              event.lead_score >= 70
                ? "text-status-green"
                : event.lead_score >= 40
                ? "text-accent-amber"
                : "text-status-red"
            }`}
          >
            {event.lead_score}
          </span>
        </div>
      </div>

      {event.outreach_context && (
        <div className="mb-4 border-l-2 border-border-default pl-4">
          <p className="text-sm text-text-secondary leading-relaxed">
            {event.outreach_context}
          </p>
        </div>
      )}

      {event.contacts.length > 0 && (
        <div className="mb-4 space-y-2">
          {event.contacts.slice(0, 3).map((c) => (
            <div key={c.id} className="flex items-center gap-3 text-sm">
              <span className="text-text-primary font-medium">
                {c.full_name}
              </span>
              {c.title && (
                <span className="text-text-tertiary">{c.title}</span>
              )}
              {c.linkedin_url && (
                <a
                  href={c.linkedin_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-accent-amber hover:underline text-xs"
                >
                  LinkedIn
                </a>
              )}
            </div>
          ))}
        </div>
      )}

      <div className="flex items-center gap-3 pt-3 border-t border-border-subtle">
        <button
          onClick={handlePushToHubspot}
          disabled={pushing}
          className="px-3 py-1.5 text-xs font-sans font-medium rounded bg-accent-amber text-surface-primary hover:opacity-90 disabled:opacity-50 transition-opacity"
        >
          {pushing ? "Pushing\u2026" : "Push to HubSpot"}
        </button>
        <button
          onClick={handleCopyOutreach}
          className="px-3 py-1.5 text-xs font-sans font-medium rounded bg-surface-overlay text-text-secondary hover:text-text-primary transition-colors"
        >
          {copied ? "Copied!" : "Copy Outreach"}
        </button>
        <button
          onClick={() => onExpand(event.project_id)}
          className="px-3 py-1.5 text-xs font-sans font-medium rounded bg-surface-overlay text-text-secondary hover:text-text-primary transition-colors ml-auto"
        >
          Details
        </button>
      </div>
    </div>
  );
}
