"use client";

import { useState } from "react";
import ConfidenceBadge from "../../epc/ConfidenceBadge";
import SourceCard from "../../epc/SourceCard";
import { EpcSource } from "@/lib/types";

interface DiscoveryApprovalCardProps {
  data: {
    discovery_id?: string;
    epc_contractor?: string;
    confidence?: string;
    sources?: EpcSource[];
    source_summary?: string[];
    assessment?: string;
    awaiting_review?: boolean;
    status?: string;
    message?: string;
    error?: string;
  };
}

function getDomain(url: string): string | null {
  if (!url || url.startsWith("search:")) return null;
  try {
    return new URL(url).hostname.replace("www.", "");
  } catch {
    return null;
  }
}

function getSourcePillHref(source: EpcSource): string | null {
  const url = source.url;
  if (url && (url.startsWith("http://") || url.startsWith("https://"))) {
    return url;
  }
  if (url && url.startsWith("search:")) {
    const query = url.slice("search:".length);
    return `https://www.google.com/search?q=${encodeURIComponent(query)}`;
  }
  if (!url && source.search_query) {
    return `https://www.google.com/search?q=${encodeURIComponent(source.search_query)}`;
  }
  return null;
}

const RELIABILITY_DOT: Record<string, string> = {
  high: "bg-emerald-400",
  medium: "bg-amber-400",
  low: "bg-red-400",
};

export default function DiscoveryApprovalCard({
  data,
}: DiscoveryApprovalCardProps) {
  const [sourcesOpen, setSourcesOpen] = useState(false);

  if (data.error) {
    return (
      <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
        Review error: {data.error}
      </div>
    );
  }

  function handleOption(text: string) {
    window.dispatchEvent(
      new CustomEvent("populate-chat-input", { detail: { text } })
    );
  }

  const isUnknown =
    !data.epc_contractor || data.epc_contractor === "Unknown";
  const sources = data.sources || [];
  const isAccepted = data.status === "accepted";
  const isRejected = data.status === "rejected";
  const hasDecision = isAccepted || isRejected;

  // Left border + background based on state
  const borderClass = isAccepted
    ? "border-l-4 border-l-emerald-400 bg-emerald-50/30"
    : isRejected
      ? "border-l-4 border-l-red-300 bg-red-50/30 opacity-75"
      : "border-l-4 border-l-amber-400";

  return (
    <div className={`rounded-lg border border-slate-200 p-4 ${borderClass}`}>
      {/* Header */}
      <div className="mb-3 flex items-center justify-between">
        <div>
          <h4 className="text-sm font-semibold text-slate-900">
            {isUnknown
              ? "EPC Not Found — Review Required"
              : data.epc_contractor}
          </h4>
        </div>
        {data.confidence && (
          <ConfidenceBadge
            confidence={data.confidence}
            sourceCount={sources.length || undefined}
            size="sm"
          />
        )}
      </div>

      {/* Source Rail — Perplexity-style pills */}
      {sources.length > 0 && (
        <div className="mb-3 flex gap-2 overflow-x-auto pb-1">
          {sources.map((s, i) => {
            const domain = getDomain(s.url || "");
            const href = getSourcePillHref(s);
            const isSearch = !domain;
            const reliabilityDot = RELIABILITY_DOT[s.reliability] || RELIABILITY_DOT.low;

            const pillContent = (
              <>
                <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-slate-200 text-[10px] font-bold text-slate-600">
                  {i + 1}
                </span>
                {isSearch ? (
                  <svg className="h-4 w-4 shrink-0 text-slate-400" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z" />
                  </svg>
                ) : (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    src={`https://www.google.com/s2/favicons?domain=${domain}&sz=16`}
                    alt=""
                    width={16}
                    height={16}
                    className="shrink-0"
                    onError={(e) => {
                      (e.target as HTMLImageElement).style.display = "none";
                    }}
                  />
                )}
                <span className="truncate text-xs text-slate-600">
                  {isSearch ? "Web search" : domain}
                </span>
                <span
                  className={`inline-block h-1.5 w-1.5 shrink-0 rounded-full ${reliabilityDot}`}
                  title={`${s.reliability} reliability`}
                />
              </>
            );

            return href ? (
              <a
                key={i}
                href={href}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-1.5 rounded-full border border-slate-200 bg-white px-2.5 py-1 transition-colors hover:border-slate-300 hover:bg-slate-50"
              >
                {pillContent}
              </a>
            ) : (
              <span
                key={i}
                className="flex items-center gap-1.5 rounded-full border border-slate-200 bg-white px-2.5 py-1"
              >
                {pillContent}
              </span>
            );
          })}
        </div>
      )}

      {/* Legacy fallback: source_summary as plain text */}
      {sources.length === 0 && data.source_summary && data.source_summary.length > 0 && (
        <div className="mb-3">
          <p className="mb-1 text-xs font-medium uppercase tracking-wide text-slate-500">
            Sources ({data.source_summary.length})
          </p>
          <ul className="space-y-0.5">
            {data.source_summary.map((s, i) => (
              <li key={i} className="text-sm text-slate-600">
                &bull; {s}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Assessment */}
      {data.assessment && (
        <div className="mb-3 rounded-md bg-white/60 px-3 py-2">
          <p className="text-xs font-medium uppercase tracking-wide text-slate-500">
            Assessment
          </p>
          <p className="mt-0.5 text-sm text-slate-700">{data.assessment}</p>
        </div>
      )}

      {/* Expandable full sources */}
      {sources.length > 0 && (
        <div className="mb-3">
          <button
            onClick={() => setSourcesOpen(!sourcesOpen)}
            className="flex items-center gap-1 text-xs font-medium text-slate-500 transition-colors hover:text-slate-700"
          >
            <svg
              className={`h-3.5 w-3.5 transition-transform ${sourcesOpen ? "rotate-90" : ""}`}
              fill="none"
              viewBox="0 0 24 24"
              strokeWidth={2}
              stroke="currentColor"
            >
              <path strokeLinecap="round" strokeLinejoin="round" d="M8.25 4.5l7.5 7.5-7.5 7.5" />
            </svg>
            View full sources ({sources.length})
          </button>
          {sourcesOpen && (
            <div className="mt-2 space-y-2">
              {sources.map((s, i) => (
                <SourceCard key={i} source={s} />
              ))}
            </div>
          )}
        </div>
      )}

      {/* Post-action status badge */}
      {hasDecision && (
        <div className="mb-2">
          {isAccepted && (
            <span className="inline-block rounded-full bg-emerald-100 px-2.5 py-0.5 text-xs font-semibold text-emerald-700">
              Confirmed
            </span>
          )}
          {isRejected && (
            <span className="inline-block rounded-full bg-red-100 px-2.5 py-0.5 text-xs font-semibold text-red-600">
              Rejected
            </span>
          )}
        </div>
      )}

      {/* Action buttons — only show if awaiting review and no decision yet */}
      {data.awaiting_review && !hasDecision && (
        <div className="flex flex-wrap gap-2">
          <button
            onClick={() => handleOption("Accept this finding")}
            className="rounded-md bg-emerald-600 px-3 py-1.5 text-xs font-medium text-white transition-colors hover:bg-emerald-700"
          >
            Accept
          </button>
          <button
            onClick={() => handleOption("Reject — ")}
            className="rounded-md border border-red-300 px-3 py-1.5 text-xs font-medium text-red-600 transition-colors hover:bg-red-50"
          >
            Reject
          </button>
          <button
            onClick={() => handleOption("Keep researching")}
            className="rounded-md border border-slate-300 px-3 py-1.5 text-xs font-medium text-slate-600 transition-colors hover:bg-slate-50"
          >
            Keep Researching
          </button>
        </div>
      )}
    </div>
  );
}
