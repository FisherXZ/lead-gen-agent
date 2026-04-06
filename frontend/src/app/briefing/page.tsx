import { createClient } from "@/lib/supabase/server";
import { BriefingFeed } from "@/components/briefing/BriefingFeed";
import type {
  AnyBriefingEvent,
  NewLeadEvent,
  ReviewEvent,
  NewProjectEvent,
  BriefingStats,
} from "@/lib/briefing-types";

export const revalidate = 300; // 5 minute ISR

export default async function BriefingPage() {
  const supabase = await createClient();

  const thirtyDaysAgo = new Date();
  thirtyDaysAgo.setDate(thirtyDaysAgo.getDate() - 30);

  const [projectsResult, discoveriesResult] = await Promise.all([
    supabase
      .from("projects")
      .select("*", { count: "exact" })
      .order("lead_score", { ascending: false })
      .limit(500),
    supabase
      .from("epc_discoveries")
      .select(
        "*, projects(id, project_name, developer, mw_capacity, iso_region, state, lead_score, construction_status, expected_cod)"
      )
      .order("created_at", { ascending: false })
      .limit(200),
  ]);

  if (projectsResult.error) {
    return (
      <main className="mx-auto max-w-7xl px-4 py-10 sm:px-6 lg:px-8">
        <p className="text-status-red">
          Failed to load projects: {projectsResult.error.message}
        </p>
      </main>
    );
  }

  const projects = projectsResult.data || [];
  const discoveries = discoveriesResult.data || [];

  // Build a set of project IDs that have discoveries
  const discoveredProjectIds = new Set(
    discoveries.map((d: any) => d.project_id)
  );

  const events: AnyBriefingEvent[] = [];

  // Accepted discoveries -> new_lead events
  for (const d of discoveries) {
    if (d.review_status !== "accepted") continue;
    const p = d.projects as any;
    if (!p) continue;
    events.push({
      id: `lead-${d.id}`,
      type: "new_lead",
      priority: 1,
      created_at: d.created_at,
      dismissed: false,
      project_id: p.id,
      project_name: p.project_name || "Unknown Project",
      developer: p.developer,
      mw_capacity: p.mw_capacity,
      iso_region: p.iso_region,
      state: p.state,
      lead_score: p.lead_score ?? 0,
      epc_contractor: d.epc_contractor,
      confidence: d.confidence,
      discovery_id: d.id,
      entity_id: null,
      contacts: [],
      outreach_context: "",
    } satisfies NewLeadEvent);
  }

  // Pending discoveries -> review events
  for (const d of discoveries) {
    if (d.review_status !== "pending") continue;
    const p = d.projects as any;
    if (!p) continue;
    events.push({
      id: `review-${d.id}`,
      type: "review",
      priority: 2,
      created_at: d.created_at,
      dismissed: false,
      project_id: p.id,
      project_name: p.project_name || "Unknown Project",
      mw_capacity: p.mw_capacity,
      iso_region: p.iso_region,
      epc_contractor: d.epc_contractor,
      confidence: d.confidence,
      discovery_id: d.id,
      reasoning_summary:
        typeof d.reasoning === "string"
          ? d.reasoning.slice(0, 200)
          : d.reasoning?.summary?.slice(0, 200) ?? "",
      source_url: d.sources?.[0]?.url ?? null,
    } satisfies ReviewEvent);
  }

  // New projects without discoveries (last 30 days)
  for (const p of projects) {
    if (discoveredProjectIds.has(p.id)) continue;
    if (new Date(p.created_at) < thirtyDaysAgo) continue;
    events.push({
      id: `project-${p.id}`,
      type: "new_project",
      priority: 3,
      created_at: p.created_at,
      dismissed: false,
      project_id: p.id,
      project_name: p.project_name || "Unknown Project",
      developer: p.developer,
      mw_capacity: p.mw_capacity,
      iso_region: p.iso_region,
      state: p.state,
      status: p.construction_status,
    } satisfies NewProjectEvent);
  }

  // Compute stats
  const oneWeekAgo = new Date();
  oneWeekAgo.setDate(oneWeekAgo.getDate() - 7);

  const stats: BriefingStats = {
    new_leads_this_week: events.filter(
      (e) =>
        e.type === "new_lead" && new Date(e.created_at) >= oneWeekAgo
    ).length,
    awaiting_review: events.filter((e) => e.type === "review").length,
    total_epcs_discovered: discoveries.filter(
      (d: any) => d.review_status === "accepted"
    ).length,
  };

  return (
    <main className="mx-auto max-w-7xl px-4 py-10 sm:px-6 lg:px-8">
      <div className="mb-6">
        <h1 className="text-2xl font-bold font-serif text-text-primary">
          Briefing
        </h1>
      </div>
      <BriefingFeed events={events} stats={stats} />
    </main>
  );
}
