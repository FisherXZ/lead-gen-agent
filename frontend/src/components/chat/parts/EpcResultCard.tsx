"use client";

import { useState } from "react";
import ConfidenceBadge from "@/components/epc/ConfidenceBadge";
import SourceCard from "@/components/epc/SourceCard";
import { EpcSource } from "@/lib/types";

interface Discovery {
  id: string;
  project_id: string;
  epc_contractor: string;
  confidence: string;
  sources: EpcSource[];
  reasoning: string | null;
  review_status: string;
}

interface EpcResultCardProps {
  data: {
    discovery?: Discovery;
    skipped?: boolean;
    reason?: string;
    error?: string;
  };
}

const AGENT_API_URL =
  process.env.NEXT_PUBLIC_AGENT_API_URL || "http://localhost:8000";

export default function EpcResultCard({ data }: EpcResultCardProps) {
  const [reviewStatus, setReviewStatus] = useState<string | null>(null);
  const [isReviewing, setIsReviewing] = useState(false);

  if (data.error) {
    return (
      <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
        Research error: {data.error}
      </div>
    );
  }

  if (data.skipped) {
    return (
      <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-700">
        Skipped — already has an accepted EPC discovery.
      </div>
    );
  }

  const discovery = data.discovery;
  if (!discovery) return null;

  const status = reviewStatus || discovery.review_status;

  async function handleReview(action: "accepted" | "rejected") {
    setIsReviewing(true);
    try {
      const res = await fetch(
        `${AGENT_API_URL}/api/discover/${discovery!.id}/review`,
        {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ action }),
        }
      );
      if (res.ok) {
        setReviewStatus(action);
      }
    } catch (err) {
      console.error("Review failed:", err);
    } finally {
      setIsReviewing(false);
    }
  }

  return (
    <div className="bg-white p-4">
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold text-slate-900">
            {discovery.epc_contractor}
          </span>
          <ConfidenceBadge confidence={discovery.confidence} />
        </div>
        {status === "accepted" && (
          <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-medium text-emerald-700">
            Accepted
          </span>
        )}
        {status === "rejected" && (
          <span className="rounded-full bg-red-100 px-2 py-0.5 text-xs font-medium text-red-700">
            Rejected
          </span>
        )}
      </div>

      {discovery.reasoning && (
        <p className="mb-3 text-sm leading-relaxed text-slate-600">
          {discovery.reasoning}
        </p>
      )}

      {discovery.sources.length > 0 && (
        <div className="mb-3 space-y-2">
          {discovery.sources.map((source, i) => (
            <SourceCard key={i} source={source} />
          ))}
        </div>
      )}

      {status === "pending" && (
        <div className="flex gap-2">
          <button
            onClick={() => handleReview("accepted")}
            disabled={isReviewing}
            className="rounded-md bg-emerald-600 px-3 py-1.5 text-xs font-medium text-white transition-colors hover:bg-emerald-700 disabled:opacity-50"
          >
            Accept
          </button>
          <button
            onClick={() => handleReview("rejected")}
            disabled={isReviewing}
            className="rounded-md bg-red-50 px-3 py-1.5 text-xs font-medium text-red-600 transition-colors hover:bg-red-100 disabled:opacity-50"
          >
            Reject
          </button>
        </div>
      )}
    </div>
  );
}
