"use client";

import { useState } from "react";
import { ReviewEvent } from "@/lib/briefing-types";
import { agentFetch } from "@/lib/agent-fetch";
import { toast } from "sonner";
import { useRouter } from "next/navigation";

interface ReviewCardProps {
  event: ReviewEvent;
  onDismiss: (eventId: string) => void;
}

export function ReviewCard({ event, onDismiss }: ReviewCardProps) {
  const [submitting, setSubmitting] = useState(false);
  const router = useRouter();

  async function handleReview(action: "accepted" | "rejected") {
    setSubmitting(true);
    try {
      const res = await agentFetch(`/api/discover/${event.discovery_id}/review`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action }),
      });
      if (!res.ok) throw new Error("Review failed");
      toast.success(action === "accepted" ? "Discovery approved" : "Discovery rejected");
      onDismiss(event.id);
    } catch {
      toast.error("Failed to submit review");
    } finally {
      setSubmitting(false);
    }
  }

  function handleInvestigate() {
    const context = `Tell me more about ${event.epc_contractor} and their involvement with ${event.project_name}`;
    router.push(`/agent?context=${encodeURIComponent(context)}`);
  }

  const confidenceColor = {
    confirmed: "text-status-green",
    likely: "text-accent-amber",
    possible: "text-text-tertiary",
    unknown: "text-text-tertiary",
  }[event.confidence];

  return (
    <div className="bg-surface-raised border border-accent-amber-muted rounded-lg p-5">
      <div className="flex items-start justify-between mb-3">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-sans font-medium uppercase tracking-wider bg-accent-amber-muted text-accent-amber">
              Needs Review
            </span>
            <span className={`text-xs font-sans font-medium capitalize ${confidenceColor}`}>
              {event.confidence}
            </span>
          </div>
          <h3 className="font-serif text-lg text-text-primary">
            {event.epc_contractor}
          </h3>
          <p className="text-sm text-text-secondary">
            {event.project_name}
            {event.mw_capacity && ` · ${event.mw_capacity} MW`}
          </p>
        </div>
      </div>

      <p className="text-sm text-text-secondary mb-4">
        {event.reasoning_summary}
        {event.source_url && /^https?:\/\//i.test(event.source_url) && (
          <>
            {" "}
            <a
              href={event.source_url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-accent-amber hover:underline"
            >
              Source
            </a>
          </>
        )}
      </p>

      <div className="flex items-center gap-3 pt-3 border-t border-border-subtle">
        <button
          onClick={() => handleReview("accepted")}
          disabled={submitting}
          className="px-3 py-1.5 text-xs font-sans font-medium rounded bg-status-green/15 text-status-green hover:bg-status-green/25 disabled:opacity-50 transition-colors"
        >
          Approve
        </button>
        <button
          onClick={() => handleReview("rejected")}
          disabled={submitting}
          className="px-3 py-1.5 text-xs font-sans font-medium rounded bg-status-red/15 text-status-red hover:bg-status-red/25 disabled:opacity-50 transition-colors"
        >
          Reject
        </button>
        <button
          onClick={handleInvestigate}
          className="px-3 py-1.5 text-xs font-sans font-medium rounded bg-surface-overlay text-text-secondary hover:text-text-primary transition-colors ml-auto"
        >
          Investigate
        </button>
      </div>
    </div>
  );
}
