// frontend/src/components/briefing/NeedsInvestigationPanel.tsx
"use client";

import { useState } from "react";
import Link from "next/link";
import { agentFetch } from "@/lib/agent-fetch";

export interface UnresearchedProject {
  id: string;
  project_name: string;
  iso_region: string;
  state: string | null;
  lead_score: number;
}

interface NeedsInvestigationPanelProps {
  projects: UnresearchedProject[];
  totalUnresearched: number;
}

export default function NeedsInvestigationPanel({
  projects: initialProjects,
  totalUnresearched,
}: NeedsInvestigationPanelProps) {
  const [projects, setProjects] =
    useState<UnresearchedProject[]>(initialProjects);
  const [researchingId, setResearchingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [completedIds, setCompletedIds] = useState<Set<string>>(new Set());

  const remaining =
    totalUnresearched - (initialProjects.length - projects.length);

  async function handleResearch(projectId: string) {
    setResearchingId(projectId);
    setError(null);
    try {
      // Step 1: Get research plan
      const planRes = await agentFetch("/api/discover/plan", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ project_id: projectId }),
      });
      if (!planRes.ok) {
        setError("Failed to generate research plan.");
        return;
      }
      const planData = await planRes.json();

      // Step 2: Execute research
      const execRes = await agentFetch("/api/discover", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ project_id: projectId, plan: planData.plan }),
      });
      if (execRes.ok) {
        setCompletedIds((prev) => new Set(prev).add(projectId));
      } else {
        setError("Research execution failed.");
      }
    } catch {
      setError("Research failed. Try again.");
    } finally {
      setResearchingId(null);
    }
  }

  return (
    <div className="rounded-lg border border-border-subtle bg-surface-raised">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-border-subtle px-4 py-3">
        <h2 className="text-[10px] font-medium uppercase tracking-widest text-text-tertiary">
          Needs Investigation
        </h2>
        <Link
          href="/projects"
          className="text-[10px] text-text-tertiary transition-colors hover:text-text-secondary"
        >
          View pipeline →
        </Link>
      </div>

      {/* Error */}
      {error && (
        <div className="border-b border-border-subtle px-4 py-2">
          <p className="text-xs text-status-red">{error}</p>
        </div>
      )}

      {/* Cards */}
      <div className="divide-y divide-border-subtle">
        {projects.length === 0 ? (
          <div className="px-4 py-8 text-center">
            <p className="text-xs text-text-tertiary">
              All projects have been researched.
            </p>
          </div>
        ) : (
          projects.map((p) => {
            const isResearching = researchingId === p.id;
            const isCompleted = completedIds.has(p.id);

            return (
              <div
                key={p.id}
                className="flex items-start justify-between px-4 py-3 transition-colors hover:bg-surface-overlay"
              >
                <Link href={`/projects/${p.id}`} className="min-w-0 flex-1">
                  <span className="font-serif text-[13px] text-text-primary">
                    {p.project_name || "Unnamed Project"}
                  </span>
                  <p className="mt-0.5 text-[10px] text-text-tertiary">
                    {p.iso_region}
                    {p.state ? ` · ${p.state}` : ""}
                    {p.lead_score > 0 ? ` · Score ${p.lead_score}` : ""}
                  </p>
                </Link>

                <div className="ml-3 shrink-0">
                  {isCompleted ? (
                    <span className="rounded-md bg-status-green/15 px-3 py-1 text-xs font-medium text-status-green">
                      Done
                    </span>
                  ) : (
                    <button
                      onClick={() => handleResearch(p.id)}
                      disabled={isResearching || researchingId !== null}
                      className="rounded-md bg-accent-amber-muted px-3 py-1 text-xs font-medium text-accent-amber transition-colors hover:bg-accent-amber/25 disabled:opacity-50"
                    >
                      {isResearching ? (
                        <span className="flex items-center gap-1.5">
                          <span className="inline-block h-3 w-3 animate-spin rounded-full border-2 border-accent-amber border-t-transparent" />
                          Researching
                        </span>
                      ) : (
                        "Research"
                      )}
                    </button>
                  )}
                </div>
              </div>
            );
          })
        )}
      </div>

      {/* Footer */}
      {remaining > projects.length && projects.length > 0 && (
        <div className="border-t border-border-subtle px-4 py-2 text-center">
          <span className="text-[10px] text-text-tertiary">
            Top by lead score · {remaining - projects.length} more
          </span>
        </div>
      )}
    </div>
  );
}
