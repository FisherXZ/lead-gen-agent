"use client";

import { useEffect, useState } from "react";

interface PlaybookStats {
  awaiting_review: number;
  new_projects_this_week: number;
  epcs_need_contacts: number;
  leads_ready_for_crm: number;
}

interface NudgeConfig {
  key: keyof PlaybookStats;
  label: string;
  color: string;
  prompt: (n: number) => string;
}

const NUDGES: NudgeConfig[] = [
  {
    key: "awaiting_review",
    label: "awaiting review",
    color: "text-accent-amber",
    prompt: (n) => `Let's triage the ${n} pending reviews`,
  },
  {
    key: "new_projects_this_week",
    label: "new projects this week",
    color: "text-status-green",
    prompt: (n) => `What's new this week? Show me the ${n} new projects`,
  },
  {
    key: "epcs_need_contacts",
    label: "EPCs need contacts",
    color: "text-text-primary",
    prompt: (n) => `Find contacts for the ${n} EPCs that need them`,
  },
  {
    key: "leads_ready_for_crm",
    label: "leads ready for CRM",
    color: "text-text-primary",
    prompt: (n) => `Let's push the ${n} ready leads to HubSpot`,
  },
];

interface OutcomeConfig {
  title: string;
  description: string;
  prompt: string;
}

const OUTCOMES: OutcomeConfig[] = [
  {
    title: "Deep-dive a company",
    description: "Research EPC, check filings, find contacts",
    prompt: "I want to deep-dive a company",
  },
  {
    title: "Batch research projects",
    description: "Run EPC discovery on multiple projects at once",
    prompt: "Batch research unresearched projects",
  },
  {
    title: "Triage the review queue",
    description: "Walk through pending discoveries one by one",
    prompt: "Let's triage pending reviews together",
  },
  {
    title: "Pipeline intelligence",
    description: "Market trends, EPC rankings, regional activity",
    prompt: "Give me a pipeline intelligence briefing",
  },
  {
    title: "Scout a new region",
    description: "What's active in a specific ISO, who's building there",
    prompt: "Scout MISO for me — what's active and who's building?",
  },
];

interface PlaybookProps {
  onSelect: (prompt: string) => void;
}

export default function Playbook({ onSelect }: PlaybookProps) {
  const [stats, setStats] = useState<PlaybookStats | null>(null);

  useEffect(() => {
    fetch("/api/playbook/stats")
      .then((res) => (res.ok ? res.json() : null))
      .then(setStats)
      .catch(() => setStats(null));
  }, []);

  const activeNudges = stats
    ? NUDGES.filter((n) => stats[n.key] > 0)
    : [];

  const allCaughtUp = stats !== null && activeNudges.length === 0;

  return (
    <div className="mx-auto w-full max-w-2xl">
      {/* Header */}
      <h2 className="mb-8 text-center font-serif text-2xl tracking-tight text-text-primary">
        Solarina
      </h2>

      {/* Two-column layout */}
      <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
        {/* Left: Right Now */}
        <div>
          <div className="mb-3 text-[10px] font-medium uppercase tracking-widest text-text-tertiary">
            Right Now
          </div>

          {stats === null ? (
            <div className="rounded-lg border border-border-subtle bg-surface-raised p-4">
              <p className="text-xs text-text-tertiary">Loading...</p>
            </div>
          ) : allCaughtUp ? (
            <div className="rounded-lg border border-border-subtle bg-surface-raised p-4 text-center">
              <p className="text-sm text-text-secondary">
                You&apos;re all caught up
              </p>
              <button
                onClick={() => onSelect("Batch research unresearched projects")}
                className="mt-2 text-xs text-accent-amber hover:underline"
              >
                Start batch research →
              </button>
            </div>
          ) : (
            <div className="space-y-2">
              {activeNudges.map((nudge) => (
                <button
                  key={nudge.key}
                  onClick={() => onSelect(nudge.prompt(stats[nudge.key]))}
                  className="flex w-full items-baseline gap-2 rounded-lg border border-border-subtle bg-surface-raised px-4 py-3 text-left transition-colors hover:border-border-default"
                >
                  <span className={`font-serif text-lg ${nudge.color}`}>
                    {stats[nudge.key]}
                  </span>
                  <span className="text-xs text-text-secondary">
                    {nudge.label}
                  </span>
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Right: Outcome cards (no header) */}
        <div className="space-y-2">
          {OUTCOMES.map((outcome) => (
            <button
              key={outcome.title}
              onClick={() => onSelect(outcome.prompt)}
              className="flex w-full flex-col rounded-lg border border-border-subtle bg-surface-raised px-4 py-3 text-left transition-colors hover:border-accent-amber-muted"
            >
              <span className="text-[13px] font-medium text-text-primary">
                {outcome.title}
              </span>
              <span className="text-[11px] text-text-tertiary">
                {outcome.description}
              </span>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
