"use client";

import { useEffect, useState } from "react";
import { Project, EpcDiscovery } from "@/lib/types";
import { createBrowserClient } from "@supabase/ssr";
import { useRouter } from "next/navigation";

interface ProjectPanelProps {
  projectId: string | null;
  onClose: () => void;
}

export function ProjectPanel({ projectId, onClose }: ProjectPanelProps) {
  const [project, setProject] = useState<Project | null>(null);
  const [discovery, setDiscovery] = useState<EpcDiscovery | null>(null);
  const [loading, setLoading] = useState(false);
  const router = useRouter();

  useEffect(() => {
    if (!projectId) return;
    setLoading(true);

    const supabase = createBrowserClient(
      process.env.NEXT_PUBLIC_SUPABASE_URL!,
      process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!
    );

    Promise.all([
      supabase.from("projects").select("*").eq("id", projectId).single(),
      supabase
        .from("epc_discoveries")
        .select("*")
        .eq("project_id", projectId)
        .order("created_at", { ascending: false })
        .limit(1)
        .maybeSingle(),
    ]).then(([projectRes, discoveryRes]) => {
      setProject(projectRes.data as Project | null);
      setDiscovery(discoveryRes.data as EpcDiscovery | null);
      setLoading(false);
    });
  }, [projectId]);

  if (!projectId) return null;

  function handleInvestigate() {
    const name = project?.project_name || "this project";
    const context = `Tell me everything about ${name}`;
    router.push(`/agent?context=${encodeURIComponent(context)}`);
  }

  return (
    <>
      <div
        className="fixed inset-0 bg-black/40 z-40"
        onClick={onClose}
      />
      <div className="fixed right-0 top-0 bottom-0 w-full max-w-lg bg-[--surface-primary] border-l border-[--border-subtle] z-50 overflow-y-auto">
        <div className="p-6">
          <button
            onClick={onClose}
            className="mb-4 text-sm text-[--text-tertiary] hover:text-[--text-secondary] transition-colors"
          >
            ← Back to Briefing
          </button>

          {loading ? (
            <div className="text-sm text-[--text-tertiary]">Loading…</div>
          ) : project ? (
            <div className="space-y-6">
              <div>
                <h2 className="font-serif text-xl text-[--text-primary] mb-1">
                  {project.project_name || project.queue_id}
                </h2>
                <div className="flex items-center gap-2 flex-wrap text-xs font-sans text-[--text-tertiary]">
                  <span>{project.iso_region}</span>
                  {project.developer && (
                    <>
                      <span>·</span>
                      <span>{project.developer}</span>
                    </>
                  )}
                  {project.mw_capacity && (
                    <>
                      <span>·</span>
                      <span>{project.mw_capacity} MW</span>
                    </>
                  )}
                  {project.state && (
                    <>
                      <span>·</span>
                      <span>{project.state}</span>
                    </>
                  )}
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <div className="text-[--text-tertiary] text-xs uppercase tracking-wider mb-1">Status</div>
                  <div className="text-[--text-primary]">
                    {project.construction_status?.replace(/_/g, " ") || "Unknown"}
                  </div>
                </div>
                <div>
                  <div className="text-[--text-tertiary] text-xs uppercase tracking-wider mb-1">Expected COD</div>
                  <div className="text-[--text-primary]">{project.expected_cod || "—"}</div>
                </div>
                <div>
                  <div className="text-[--text-tertiary] text-xs uppercase tracking-wider mb-1">Lead Score</div>
                  <div className="text-[--text-primary] font-mono">{project.lead_score}</div>
                </div>
                <div>
                  <div className="text-[--text-tertiary] text-xs uppercase tracking-wider mb-1">Fuel Type</div>
                  <div className="text-[--text-primary]">{project.fuel_type || "—"}</div>
                </div>
              </div>

              {discovery && (
                <div className="pt-4 border-t border-[--border-subtle]">
                  <div className="text-[--text-tertiary] text-xs uppercase tracking-wider mb-2">EPC Discovery</div>
                  <div className="text-[--text-primary] font-medium mb-1">{discovery.epc_contractor}</div>
                  <div className="text-sm text-[--text-secondary]">
                    Confidence: <span className="capitalize">{discovery.confidence}</span>
                    {" · "}Review: <span className="capitalize">{discovery.review_status}</span>
                  </div>
                </div>
              )}

              {(project.latitude || project.longitude) && (
                <div className="pt-4 border-t border-[--border-subtle]">
                  <div className="text-[--text-tertiary] text-xs uppercase tracking-wider mb-2">Location</div>
                  <p className="text-sm text-[--text-secondary]">
                    {project.county && `${project.county}, `}{project.state}
                  </p>
                  {project.latitude && project.longitude && (
                    <a
                      href={`https://www.google.com/maps?q=${project.latitude},${project.longitude}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-xs text-[--accent-amber] hover:underline mt-1 inline-block"
                    >
                      View on Google Maps
                    </a>
                  )}
                </div>
              )}

              <div className="pt-4 border-t border-[--border-subtle] flex gap-3">
                <button
                  onClick={handleInvestigate}
                  className="px-3 py-1.5 text-xs font-sans font-medium rounded bg-[--accent-amber] text-[--surface-primary] hover:opacity-90 transition-opacity"
                >
                  Investigate in Chat
                </button>
              </div>
            </div>
          ) : (
            <div className="text-sm text-[--text-tertiary]">Project not found.</div>
          )}
        </div>
      </div>
    </>
  );
}
