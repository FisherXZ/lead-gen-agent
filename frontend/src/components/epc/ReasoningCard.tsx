"use client";

import { useState } from "react";
import { EpcSource } from "@/lib/types";
import SourceCard from "./SourceCard";

/* ------------------------------------------------------------------ */
/*  Parse reasoning text into structured insight blocks                */
/* ------------------------------------------------------------------ */

interface Insight {
  type: "finding" | "context" | "conclusion";
  text: string;
}

/**
 * Splits a wall-of-text reasoning paragraph into digestible insight blocks.
 * Uses sentence-level heuristics to categorize:
 *   - finding: sentences about what was/wasn't found
 *   - conclusion: sentences with "likely", "therefore", "given", "either"
 *   - context: everything else (project background)
 */
function parseReasoning(raw: string): Insight[] {
  // Split on sentence boundaries (period followed by space + uppercase)
  const sentences = raw
    .replace(/\n+/g, " ")
    .split(/(?<=\.)\s+(?=[A-Z])/)
    .map((s) => s.trim())
    .filter(Boolean);

  if (sentences.length === 0) return [{ type: "context", text: raw }];

  const insights: Insight[] = [];
  let currentType: Insight["type"] | null = null;
  let buffer: string[] = [];

  function flush() {
    if (buffer.length > 0 && currentType) {
      insights.push({ type: currentType, text: buffer.join(" ") });
      buffer = [];
    }
  }

  for (const sentence of sentences) {
    const lower = sentence.toLowerCase();

    let type: Insight["type"];
    if (
      /\b(likely|therefore|given|either|suggest|conclude|appears?|indicating)\b/.test(lower) &&
      !/\b(search|found|returned|no .* was found)\b/.test(lower)
    ) {
      type = "conclusion";
    } else if (
      /\b(no .* (found|identified)|not .* found|search(es)? returned|could not|couldn't|all searches|did not find|hasn't|has not|without)\b/.test(lower) ||
      /\b(found|identified|confirmed|shows?|indicates?|reveals?)\b/.test(lower)
    ) {
      type = "finding";
    } else {
      type = "context";
    }

    if (type !== currentType) {
      flush();
      currentType = type;
    }
    buffer.push(sentence);
  }
  flush();

  return insights;
}

/* ------------------------------------------------------------------ */
/*  Visual helpers                                                     */
/* ------------------------------------------------------------------ */

const INSIGHT_CONFIG: Record<
  Insight["type"],
  { icon: React.ReactNode; label: string; border: string; bg: string; iconBg: string }
> = {
  context: {
    label: "Project Context",
    border: "border-slate-200",
    bg: "bg-slate-50",
    iconBg: "bg-slate-100",
    icon: (
      <svg className="h-3.5 w-3.5 text-slate-500" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" d="M11.25 11.25l.041-.02a.75.75 0 011.063.852l-.708 2.836a.75.75 0 001.063.853l.041-.021M21 12a9 9 0 11-18 0 9 9 0 0118 0zm-9-3.75h.008v.008H12V8.25z" />
      </svg>
    ),
  },
  finding: {
    label: "Key Findings",
    border: "border-amber-200",
    bg: "bg-amber-50",
    iconBg: "bg-amber-100",
    icon: (
      <svg className="h-3.5 w-3.5 text-amber-600" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z" />
      </svg>
    ),
  },
  conclusion: {
    label: "Assessment",
    border: "border-emerald-200",
    bg: "bg-emerald-50",
    iconBg: "bg-emerald-100",
    icon: (
      <svg className="h-3.5 w-3.5 text-emerald-600" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" d="M12 18v-5.25m0 0a6.01 6.01 0 001.5-.189m-1.5.189a6.01 6.01 0 01-1.5-.189m3.75 7.478a12.06 12.06 0 01-4.5 0m3.75 2.383a14.406 14.406 0 01-3 0M14.25 18v-.192c0-.983.658-1.823 1.508-2.316a7.5 7.5 0 10-7.517 0c.85.493 1.509 1.333 1.509 2.316V18" />
      </svg>
    ),
  },
};

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

export default function ReasoningCard({
  reasoning,
  sources,
}: {
  reasoning: string | null;
  sources: EpcSource[];
}) {
  const [sourcesOpen, setSourcesOpen] = useState(false);

  if (!reasoning && sources.length === 0) return null;

  const insights = reasoning ? parseReasoning(reasoning) : [];

  // Group all insights by type into at most 3 cards (no info lost, just consolidated)
  const typeOrder: Insight["type"][] = ["context", "finding", "conclusion"];
  const grouped = typeOrder
    .map((type) => {
      const texts = insights.filter((i) => i.type === type).map((i) => i.text);
      if (texts.length === 0) return null;
      return { type, text: texts.join(" ") } as Insight;
    })
    .filter(Boolean) as Insight[];

  return (
    <div className="max-w-2xl overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm">
      {/* Header */}
      <div className="border-b border-slate-200 bg-slate-50 px-4 py-3">
        <div className="flex items-center gap-2">
          <div className="flex h-6 w-6 items-center justify-center rounded-full bg-amber-100">
            <svg className="h-3.5 w-3.5 text-amber-600" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09zM18.259 8.715L18 9.75l-.259-1.035a3.375 3.375 0 00-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 002.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 002.455 2.456L21.75 6l-1.036.259a3.375 3.375 0 00-2.455 2.456z" />
            </svg>
          </div>
          <p className="text-xs font-medium uppercase tracking-wide text-slate-500">
            Research Analysis
          </p>
        </div>
      </div>

      {/* Insight blocks */}
      {grouped.length > 0 && (
        <div className="flex flex-col gap-3 p-4">
          {grouped.map((insight, i) => {
            const config = INSIGHT_CONFIG[insight.type];
            return (
              <div
                key={i}
                className={`rounded-lg border ${config.border} ${config.bg} p-3`}
              >
                <div className="mb-1.5 flex items-center gap-1.5">
                  <div className={`flex h-5 w-5 items-center justify-center rounded-full ${config.iconBg}`}>
                    {config.icon}
                  </div>
                  <span className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                    {config.label}
                  </span>
                </div>
                <p className="text-sm leading-relaxed text-slate-700">
                  {insight.text}
                </p>
              </div>
            );
          })}
        </div>
      )}

      {/* Sources — collapsible */}
      {sources.length > 0 && (
        <div className="border-t border-slate-200">
          <button
            type="button"
            onClick={() => setSourcesOpen(!sourcesOpen)}
            className="flex w-full items-center gap-2 px-4 py-3 text-left transition-colors hover:bg-slate-50"
          >
            <svg className="h-4 w-4 text-slate-400" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M13.19 8.688a4.5 4.5 0 011.242 7.244l-4.5 4.5a4.5 4.5 0 01-6.364-6.364l1.757-1.757m13.35-.622l1.757-1.757a4.5 4.5 0 00-6.364-6.364l-4.5 4.5a4.5 4.5 0 001.242 7.244" />
            </svg>
            <span className="flex-1 text-sm font-medium text-slate-700">
              Sources ({sources.length})
            </span>
            <svg
              className={`h-4 w-4 text-slate-400 transition-transform duration-200 ${sourcesOpen ? "rotate-180" : ""}`}
              fill="none"
              viewBox="0 0 24 24"
              strokeWidth={2}
              stroke="currentColor"
            >
              <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 8.25l-7.5 7.5-7.5-7.5" />
            </svg>
          </button>
          {sourcesOpen && (
            <div className="flex flex-col gap-2 px-4 pb-4">
              {sources.map((source, i) => (
                <SourceCard key={i} source={source} />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
